#!/bin/bash
set -euxo pipefail

REGION="${AWS_REGION:-ca-central-1}"
ACCOUNT="${AWS_ACCOUNT_ID:-045064752988}"
IMAGE="${NEXUSLEAD_IMAGE:-$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/nexuslead-ai:latest}"
APP_DIR="/opt/nexuslead"
LOG_GROUP="/nexuslead-ai/ec2"

mkdir -p "$APP_DIR"

if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

dnf update -y
dnf install -y docker awscli cronie python3
systemctl enable --now docker
systemctl enable --now crond
usermod -aG docker ec2-user || true

if [ ! -f "$APP_DIR/.env" ]; then
  PG_PASSWORD=$(openssl rand -hex 16)
  SESSION_SECRET=$(openssl rand -hex 32)
  cat > "$APP_DIR/.env" <<ENV
POSTGRES_PASSWORD=$PG_PASSWORD
DATABASE_URL=postgresql://nexuslead:$PG_PASSWORD@nexuslead-postgres:5432/nexuslead
NEXUSLEAD_SESSION_SECRET=$SESSION_SECRET
NEXUSLEAD_UPLOAD_DIR=/app/uploads
NEXUSLEAD_EMAIL_PROVIDER=console
LOG_LEVEL=INFO
PORT=8000
ENV
  chmod 600 "$APP_DIR/.env"
fi

cat > "$APP_DIR/deploy.sh" <<'DEPLOY'
#!/bin/bash
set -euxo pipefail

REGION="${AWS_REGION:-ca-central-1}"
ACCOUNT="${AWS_ACCOUNT_ID:-045064752988}"
IMAGE="${NEXUSLEAD_IMAGE:-$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/nexuslead-ai:latest}"
APP_DIR="/opt/nexuslead"
LOG_GROUP="/nexuslead-ai/ec2"

set -a
. "$APP_DIR/.env"
set +a

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
docker network create nexuslead-net || true
docker volume create nexuslead-postgres || true
docker volume create nexuslead-uploads || true

if ! docker ps --format '{{.Names}}' | grep -qx nexuslead-postgres; then
  docker rm -f nexuslead-postgres || true
  docker run -d --name nexuslead-postgres --network nexuslead-net --network-alias postgres --restart unless-stopped \
    -e POSTGRES_USER=nexuslead \
    -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -e POSTGRES_DB=nexuslead \
    -v nexuslead-postgres:/var/lib/postgresql/data \
    postgres:16-alpine \
    -c shared_buffers=32MB -c max_connections=20
fi

for i in $(seq 1 60); do
  if docker exec nexuslead-postgres pg_isready -U nexuslead -d nexuslead; then break; fi
  sleep 2
done

docker pull "$IMAGE"
docker rm -f nexuslead-ai || true
docker run -d --name nexuslead-ai --network nexuslead-net --restart unless-stopped \
  --env-file "$APP_DIR/.env" \
  -p 80:8000 \
  -v nexuslead-uploads:/app/uploads \
  --log-driver=awslogs \
  --log-opt awslogs-region="$REGION" \
  --log-opt awslogs-group="$LOG_GROUP" \
  --log-opt awslogs-stream="nexuslead-ai" \
  --log-opt awslogs-create-group=true \
  "$IMAGE"
DEPLOY
chmod +x "$APP_DIR/deploy.sh"

"$APP_DIR/deploy.sh"

cat > /etc/cron.d/nexuslead-deploy <<'CRON'
SHELL=/bin/bash
PATH=/sbin:/bin:/usr/sbin:/usr/bin:/usr/local/bin
*/10 * * * * root /opt/nexuslead/deploy.sh >> /var/log/nexuslead-deploy.log 2>&1
CRON

cat > "$APP_DIR/smoke.py" <<'SMOKE'
#!/usr/bin/env python3
import http.cookiejar
import json
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1"


class Session:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def get(self, path):
        with self.opener.open(BASE + path, timeout=20) as response:
            return response.status, response.read().decode("utf-8", errors="replace")

    def post(self, path, data):
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(BASE + path, data=encoded, method="POST")
        with self.opener.open(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8", errors="replace")


def wait_for_health():
    for _ in range(60):
        try:
            status, body = Session().get("/health")
            if status == 200 and '"status":"ready"' in body.replace(" ", ""):
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("health check did not become ready")


def login(email, password):
    session = Session()
    session.post("/login", {"email": email, "password": password})
    status, body = session.get("/api/auth/me")
    if status != 200 or email not in body:
        raise RuntimeError(f"login failed for {email}")
    return session


def api_json(session, path):
    status, body = session.get(path)
    if status != 200:
        raise RuntimeError(f"{path} returned {status}")
    return json.loads(body)


def main():
    wait_for_health()
    suffix = str(int(time.time()))
    admin = login("admin@nextrns.local", "admin123")
    manager = login("manager@nextrns.local", "manager123")
    agent = login("agent@nextrns.local", "agent123")

    for path in ["/", "/login", "/dashboard", "/api/analytics", "/reports/daily"]:
        status, _ = admin.get(path)
        if status != 200:
            raise RuntimeError(f"{path} returned {status}")

    client_name = f"EC2 Smoke Client {suffix}"
    admin.post(
        "/clients",
        {
            "name": client_name,
            "category": "Carpenter",
            "city": "Toronto",
            "service_area": "Toronto",
            "min_budget": "100",
            "max_budget": "5000",
            "contact_email": "ops+ec2-smoke@nextrns.local",
            "notes": "One-time EC2 smoke verification client",
        },
    )
    clients = api_json(admin, "/api/clients")
    if not any(client["name"] == client_name for client in clients):
        raise RuntimeError("client creation verification failed")

    context = f"EC2 smoke lead {suffix}"
    admin.post(
        "/leads",
        {
            "source": "Manual intake",
            "category": "Carpenter",
            "city": "Toronto",
            "context": context,
            "budget": "2500",
            "owner": "Unassigned",
            "due_date": "",
        },
    )
    leads = api_json(admin, "/api/leads")
    lead = next((item for item in leads if item["context"] == context), None)
    if not lead:
        raise RuntimeError("lead creation verification failed")

    lead_id = str(lead["id"])
    manager.post(f"/leads/{lead_id}/assign", {"owner": "Lead Operations Agent"})
    manager.post(f"/leads/{lead_id}/approve", {})
    agent.post(f"/leads/{lead_id}/status", {"status": "Follow-up", "note": "EC2 smoke status update"})
    admin.post("/reviews", {"client_id": "1", "rating": "2", "text": "Slow response smoke check", "source": "EC2 smoke"})

    tasks = api_json(agent, "/api/tasks")
    if tasks:
        agent.post(f"/tasks/{tasks[0]['id']}/close", {})

    for path in ["/export/leads.csv", "/export/google-sheets.csv", "/export/tasks.csv"]:
        status, _ = admin.get(path)
        if status != 200:
            raise RuntimeError(f"{path} returned {status}")

    print(f"NEXUSLEAD_SMOKE_OK suffix={suffix} lead_id={lead_id} clients={len(clients)} leads={len(leads)}", flush=True)


if __name__ == "__main__":
    main()
SMOKE
chmod +x "$APP_DIR/smoke.py"
"$APP_DIR/smoke.py" 2>&1 | tee -a /var/log/nexuslead-smoke.log /dev/console || true
