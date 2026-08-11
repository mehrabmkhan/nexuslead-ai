#!/bin/bash
set -euo pipefail

REGION="${AWS_REGION:-ca-central-1}"
ACCOUNT="${AWS_ACCOUNT_ID:-045064752988}"
IMAGE="${NEXUSLEAD_IMAGE:-$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/nexuslead-ai:latest}"
APP_DIR="/opt/nexuslead"
LOG_GROUP="/nexuslead-ai/ec2"
HTTPS_DOMAIN="${NEXUSLEAD_HTTPS_DOMAIN:-99-79-66-16.sslip.io}"
RAW_HOST="${NEXUSLEAD_RAW_HOST:-ec2-99-79-66-16.ca-central-1.compute.amazonaws.com}"

mkdir -p "$APP_DIR"
if [ "${0:-}" != "$APP_DIR/deploy.sh" ]; then
  cp "$0" "$APP_DIR/deploy.sh"
  chmod +x "$APP_DIR/deploy.sh"
fi

if [ ! -f "$APP_DIR/.env" ]; then
  PG_PASSWORD=$(openssl rand -hex 16)
  SESSION_SECRET=$(openssl rand -hex 32)
  cat > "$APP_DIR/.env" <<ENV
POSTGRES_PASSWORD=$PG_PASSWORD
DATABASE_URL=postgresql://nexuslead:$PG_PASSWORD@nexuslead-postgres:5432/nexuslead
NEXUSLEAD_SESSION_SECRET=$SESSION_SECRET
NEXUSLEAD_UPLOAD_DIR=/app/uploads
NEXUSLEAD_EMAIL_PROVIDER=console
NEXUSLEAD_SECURE_COOKIES=true
LOG_LEVEL=INFO
PORT=8000
ENV
  chmod 600 "$APP_DIR/.env"
fi

if ! grep -q '^NEXUSLEAD_SECURE_COOKIES=' "$APP_DIR/.env"; then
  echo 'NEXUSLEAD_SECURE_COOKIES=true' >> "$APP_DIR/.env"
else
  sed -i 's/^NEXUSLEAD_SECURE_COOKIES=.*/NEXUSLEAD_SECURE_COOKIES=true/' "$APP_DIR/.env"
fi

set -a
. "$APP_DIR/.env"
set +a

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com" >/dev/null
docker network create nexuslead-net >/dev/null 2>&1 || true
docker volume create nexuslead-postgres >/dev/null
docker volume create nexuslead-uploads >/dev/null
docker volume create nexuslead-caddy-data >/dev/null
docker volume create nexuslead-caddy-config >/dev/null

if ! docker ps --format '{{.Names}}' | grep -qx nexuslead-postgres; then
  docker rm -f nexuslead-postgres >/dev/null 2>&1 || true
  docker run -d --name nexuslead-postgres --network nexuslead-net --network-alias postgres --restart unless-stopped \
    -e POSTGRES_USER=nexuslead \
    -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -e POSTGRES_DB=nexuslead \
    -v nexuslead-postgres:/var/lib/postgresql/data \
    postgres:16-alpine \
    -c shared_buffers=32MB -c max_connections=20 >/dev/null
fi

for _ in $(seq 1 60); do
  if docker exec nexuslead-postgres pg_isready -U nexuslead -d nexuslead >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

docker pull "$IMAGE"

previous_image="$(docker inspect --format='{{.Image}}' nexuslead-ai 2>/dev/null || true)"
docker rm -f nexuslead-ai-candidate >/dev/null 2>&1 || true
docker run -d --name nexuslead-ai-candidate --network nexuslead-net --restart unless-stopped \
  --env-file "$APP_DIR/.env" \
  -v nexuslead-uploads:/app/uploads \
  --log-driver=awslogs \
  --log-opt awslogs-region="$REGION" \
  --log-opt awslogs-group="$LOG_GROUP" \
  --log-opt awslogs-stream="nexuslead-ai" \
  --log-opt awslogs-create-group=true \
  "$IMAGE" >/dev/null

for _ in $(seq 1 40); do
  if docker exec nexuslead-ai-candidate python - <<'PY' >/dev/null 2>&1
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5) as response:
    payload = json.loads(response.read().decode("utf-8"))
    raise SystemExit(0 if payload.get("status") == "ready" else 1)
PY
  then
    candidate_ok=true
    break
  fi
  sleep 3
done

if [ "${candidate_ok:-false}" != "true" ]; then
  docker logs --tail 100 nexuslead-ai-candidate || true
  docker rm -f nexuslead-ai-candidate >/dev/null 2>&1 || true
  if [ -n "$previous_image" ]; then
    docker rm -f nexuslead-ai >/dev/null 2>&1 || true
    docker run -d --name nexuslead-ai --network nexuslead-net --restart unless-stopped \
      --env-file "$APP_DIR/.env" \
      -v nexuslead-uploads:/app/uploads \
      --log-driver=awslogs \
      --log-opt awslogs-region="$REGION" \
      --log-opt awslogs-group="$LOG_GROUP" \
      --log-opt awslogs-stream="nexuslead-ai" \
      --log-opt awslogs-create-group=true \
      "$previous_image" >/dev/null
  fi
  echo "NEXUSLEAD_DEPLOY_FAILED health check failed; rollback attempted"
  exit 1
fi

docker rm -f nexuslead-ai >/dev/null 2>&1 || true
docker rename nexuslead-ai-candidate nexuslead-ai
docker update --restart unless-stopped nexuslead-ai >/dev/null

cat > "$APP_DIR/Caddyfile" <<CADDY
$HTTPS_DOMAIN {
  encode gzip
  header {
    Strict-Transport-Security "max-age=31536000"
    X-Content-Type-Options "nosniff"
    X-Frame-Options "DENY"
    Referrer-Policy "strict-origin-when-cross-origin"
  }
  reverse_proxy nexuslead-ai:8000
}

http://$RAW_HOST {
  reverse_proxy nexuslead-ai:8000
}
CADDY

docker rm -f nexuslead-proxy >/dev/null 2>&1 || true
docker pull caddy:2-alpine
docker run -d --name nexuslead-proxy --network nexuslead-net --restart unless-stopped \
  -p 80:80 -p 443:443 \
  -v "$APP_DIR/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -v nexuslead-caddy-data:/data \
  -v nexuslead-caddy-config:/config \
  caddy:2-alpine >/dev/null

cat > "$APP_DIR/backup-postgres.sh" <<'BACKUP'
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/opt/nexuslead/backups"
mkdir -p "$BACKUP_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
docker exec nexuslead-postgres pg_dump -U nexuslead -d nexuslead | gzip > "$BACKUP_DIR/nexuslead-$timestamp.sql.gz"
find "$BACKUP_DIR" -type f -name 'nexuslead-*.sql.gz' -mtime +7 -delete
echo "NEXUSLEAD_BACKUP_OK $BACKUP_DIR/nexuslead-$timestamp.sql.gz"
BACKUP
chmod +x "$APP_DIR/backup-postgres.sh"
cat > /etc/cron.d/nexuslead-backup <<'CRON'
SHELL=/bin/bash
PATH=/sbin:/bin:/usr/sbin:/usr/bin:/usr/local/bin
17 6 * * * root /opt/nexuslead/backup-postgres.sh >> /var/log/nexuslead-backup.log 2>&1
CRON
"$APP_DIR/backup-postgres.sh"

for _ in $(seq 1 40); do
  if docker exec nexuslead-proxy wget -qO- "http://nexuslead-ai:8000/health" | grep -q '"status":"ready"'; then
    echo "NEXUSLEAD_DEPLOY_OK image=$IMAGE https_domain=$HTTPS_DOMAIN"
    exit 0
  fi
  sleep 3
done

echo "NEXUSLEAD_DEPLOY_FAILED proxy health check failed"
exit 1
