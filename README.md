# NexusLead AI

NexusLead AI is an internal B2B lead operations platform for NextRNS-style BPO teams. It gives admins, managers, and lead generation specialists a daily workspace for lead intake, qualification, client matching, outreach draft review, follow-up tasks, reporting, and exports.

Live URL: https://nexuslead-ai.onrender.com

## Product Scope

NexusLead AI is designed for approved operational inputs:

- Manual lead entry
- CSV upload
- Google Sheets-ready CSV export/import
- Approved CRM imports
- Public business directories where terms allow access
- Official APIs where available
- n8n workflows using approved integrations

Outreach remains human-reviewed before sending. The app does not implement auto-comment spam, ban-evasion, scraping bypasses, or automated outbound sending.

## Core Capabilities

- Login with Admin, Manager, and Agent roles
- Admin controls for clients, users, exports, analytics, and job readiness
- Manager workflow for lead review, draft approval, and agent assignment
- Agent workflow for lead creation, status updates, notes, attachments, and assigned task export
- Multi-tenant client profiles with business type, service area, city, budget range, contact email, and notes
- Deterministic lead scoring, priority classification, and client matching
- CSV import, Google Sheets-ready CSV export, and follow-up task CSV export
- Outreach draft generation with human approval status
- Notes/history, audit logging, task due dates, and file attachment metadata
- Mock email notification service for local development
- Background job registry ready for scheduled checks, reports, and reminders
- Health and metrics endpoints for monitoring
- FastAPI Swagger/OpenAPI docs at `/docs`

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://localhost:8000/login
```

Default local users:

```text
Admin: admin@nextrns.local / admin123
Manager: manager@nextrns.local / manager123
Agent: agent@nextrns.local / agent123
```

## Useful Routes

- `/login`
- `/dashboard`
- `/docs`
- `/api/auth/me`
- `/api/leads`
- `/api/clients`
- `/api/tasks`
- `/api/analytics`
- `/export/leads.csv`
- `/export/tasks.csv`
- `/export/google-sheets.csv`
- `/reports/daily`
- `/health`
- `/metrics`
- `/jobs/status`

## Environment Variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `NEXUSLEAD_DB` | No | SQLite database path. Defaults to `data/nexuslead.db`. |
| `DATABASE_URL` | Production | PostgreSQL connection string for hosted deployments after migrations are applied. |
| `NEXUSLEAD_SESSION_SECRET` | Production | Secret used to sign login sessions. |
| `NEXUSLEAD_UPLOAD_DIR` | No | Local upload storage path. Defaults to `uploads`. |
| `NEXUSLEAD_EMAIL_PROVIDER` | No | `console` locally; future providers can map to SendGrid or AWS SES. |
| `PORT` | Hosting | Port supplied by Render, Fly.io, or another host. |

## Database And Migrations

SQLite is the local development database. The app initializes required tables on startup for the MVP.

For production PostgreSQL, use a hosted database such as Neon, Supabase, or Render PostgreSQL, set `DATABASE_URL`, and apply a real migration tool before enabling a production driver. Recommended next step:

```bash
python -m pip install alembic psycopg[binary]
alembic init migrations
```

Then translate the schema in `app/database.py` into Alembic migration files. See [docs/operations.md](docs/operations.md) for the production migration path.

## Docker

```bash
docker compose up --build
```

Open `http://localhost:8000/login`.

## Production Start Command

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

On Windows PowerShell locally, use `$env:PORT=8000` or run the explicit port command from the local setup.

## Live Demo Deployment

Live application: https://nexuslead-ai.onrender.com

NexusLead AI is deployed on Render Free as a server-rendered FastAPI web service. Netlify/Vercel are better for separate static frontends; Render/Fly.io are the better fit for this backend-rendered MVP.

Deployment architecture:

- GitHub repository: `mehrabmkhan/nexuslead-ai`
- Render service: `nexuslead-ai`
- Service type: Web Service
- Runtime: Python
- Plan: Free
- Region: Oregon
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`
- Public routes: `/login`, `/dashboard`, `/docs`, `/health`, `/metrics`
- Storage: SQLite local MVP database at `data/nexuslead.db` on Render's ephemeral filesystem
- Future production database: Neon, Supabase, or Render PostgreSQL via `DATABASE_URL` after migrations are added

Render environment variables:

| Variable | Value |
| --- | --- |
| `NEXUSLEAD_SESSION_SECRET` | Set in Render service environment |
| `NEXUSLEAD_UPLOAD_DIR` | `uploads` |
| `NEXUSLEAD_EMAIL_PROVIDER` | `console` |
| `PORT` | Provided by Render |

Deployment instructions:

1. Push changes to `main`.
2. Render auto-deploys from GitHub commits.
3. If deploying manually, run `render deploys create <service-id> --wait`.
4. Verify `https://nexuslead-ai.onrender.com/health` returns `status: ready`.
5. Verify login and dashboard at `https://nexuslead-ai.onrender.com/login`.

## Testing

```bash
python -m pytest
```

GitHub Actions runs the same test suite on push and pull request.

## Integration Docs

- [Operations, jobs, email, calendar, monitoring, and migrations](docs/operations.md)
- [Google Sheets and n8n workflows](docs/n8n-expansion.md)
- [Compliance model](docs/compliance.md)
- [Architecture](docs/architecture.md)
- [Deployment](docs/deployment.md)
