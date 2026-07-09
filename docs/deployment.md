# Deployment

NexusLead AI is deployed publicly on Render Free:

```text
https://nexuslead-ai.onrender.com
```

The app is a server-rendered FastAPI service, so Render/Fly.io style hosting is a better fit than static hosts such as Netlify or Vercel for this MVP.

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
| `NEXUSLEAD_EMAIL_PROVIDER` | `console` for the MVP/mock notification provider |
| `PORT` | Provided by Render |
| `DATABASE_URL` | Future PostgreSQL connection string after migrations are implemented |

## Verification Checklist

After each deployment:

1. Open `https://nexuslead-ai.onrender.com` and confirm the login UI appears.
2. Confirm `/health` returns `status: ready`.
3. Sign in as Admin, Manager, and Agent.
4. Confirm the dashboard loads for each role.
5. Create or update a lead.
6. Export leads and tasks CSVs.
7. Open `/docs` to confirm the OpenAPI UI is available.

## MVP Storage Note

The current deployed app uses SQLite on Render's ephemeral filesystem. This is acceptable for a live portfolio MVP but not for durable production data. A production version should use PostgreSQL with migrations and external object storage for file uploads.

## Docker

```bash
docker compose up --build
```

Open `http://localhost:8000`.

## Manual Start Command

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
