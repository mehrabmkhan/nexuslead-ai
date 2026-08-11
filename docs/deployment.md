# Deployment

NexusLead AI is deployed on AWS EC2 as the primary deployment and Render Free as the fallback deployment:

```text
AWS EC2: http://ec2-99-79-66-16.ca-central-1.compute.amazonaws.com
Render fallback: https://nexuslead-ai.onrender.com
```

## AWS Primary Deployment

Use the Dockerfile with Amazon ECR and the single-instance EC2 bootstrap in `scripts/aws/ec2-user-data.sh`.

| Setting | Value |
| --- | --- |
| Runtime | Docker |
| Image repository | Amazon ECR `nexuslead-ai` |
| Container port | `8000` |
| Start command | `scripts/start.sh` |
| Health check path | `/health` |
| Logs | CloudWatch log group `/nexuslead-ai/ec2` |
| Database | PostgreSQL through `DATABASE_URL`, backed by Docker volume `nexuslead-postgres` |

See [aws-deployment.md](aws-deployment.md) for the full runbook.

## Render Fallback

```text
https://nexuslead-ai.onrender.com
```

The app is a server-rendered FastAPI service, so Render/Fly.io style hosting remains a better fallback than static hosts such as Netlify or Vercel.

## Render Service

| Setting | Value |
| --- | --- |
| Service name | `nexuslead-ai` |
| Service type | Web Service |
| Runtime | Python |
| Plan | Free |
| Region | Oregon |
| Repository | `mehrabmkhan/nexuslead-ai` |
| Branch | `main` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `NEXUSLEAD_SESSION_SECRET` | Secret used to sign login sessions |
| `NEXUSLEAD_UPLOAD_DIR` | Local upload metadata directory, defaults to `uploads` |
| `NEXUSLEAD_EMAIL_PROVIDER` | `console` for local notification behavior |
| `PORT` | Provided by Render |
| `DATABASE_URL` | PostgreSQL connection string in production |
| `LOG_LEVEL` | Runtime logging level |

## Verification Checklist

After each deployment:

1. Open `http://ec2-99-79-66-16.ca-central-1.compute.amazonaws.com` and confirm the login UI appears.
2. Confirm `/health` returns `status: ready`.
3. Sign in as Admin, Manager, and Agent.
4. Confirm the dashboard loads for each role.
5. Create or update a lead.
6. Export leads and tasks CSVs.
7. Open `/docs` to confirm the OpenAPI UI is available.

## Storage Note

Local development uses SQLite. AWS production should use PostgreSQL and the included Alembic migrations. File uploads currently store metadata and local files; use S3 or another object store for durable uploaded files.

## Docker

```bash
docker compose up --build
```

Open `http://localhost:8000`.

## Manual Start Command

```bash
scripts/start.sh
```
