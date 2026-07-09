# NexusLead AI

NexusLead AI is a deployed internal B2B lead operations MVP for NextRNS-style BPO teams. It gives admins, managers, and lead generation specialists a shared workspace for lead intake, qualification, client matching, human-reviewed outreach drafts, follow-up tasks, reporting, and CSV exports.

This repository is a working portfolio MVP, not a claim of production customer adoption. The live app uses approved sample data and is intended to demonstrate product, engineering, deployment, and operations readiness.

## Live Demo

Live application: https://nexuslead-ai.onrender.com

Demo credentials:

| Role | Email | Password | What to review |
| --- | --- | --- | --- |
| Admin | `admin@nextrns.local` | `admin123` | Full workspace, users, clients, exports, analytics |
| Manager | `manager@nextrns.local` | `manager123` | Lead review, draft approval, assignment, analytics |
| Agent | `agent@nextrns.local` | `agent123` | Assigned lead workflow, notes, statuses, task export |

Useful live routes:

- App entry: https://nexuslead-ai.onrender.com
- Login: https://nexuslead-ai.onrender.com/login
- Dashboard: https://nexuslead-ai.onrender.com/dashboard
- API docs: https://nexuslead-ai.onrender.com/docs
- Health check: https://nexuslead-ai.onrender.com/health
- Metrics: https://nexuslead-ai.onrender.com/metrics

## Screenshots

### Login and Demo Entry

![NexusLead AI login screen](screenshots/login.png)

### Operations Dashboard

![NexusLead AI operations dashboard](screenshots/dashboard.png)

## Feature Walkthrough

1. Sign in with one of the demo roles.
2. Review KPI cards for active leads, high-priority leads, follow-ups, conversion, and estimated opportunity value.
3. Use search and filters to narrow the lead pipeline by client, city, business type, priority, and status.
4. Create a lead through the lead intake form.
5. Review the deterministic score, matched client, priority badge, and outreach draft.
6. Update status, add notes, assign ownership, attach file metadata, or approve an outreach draft depending on role.
7. Review follow-up tasks, client profile cards, pipeline analytics, lead category charts, and audit activity.
8. Export leads, tasks, Google Sheets-ready CSV, or the daily report.

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

- Admin, Manager, and Agent roles
- Role-based dashboard behavior
- Multi-tenant client profiles with business type, service area, city, budget range, contact email, and notes
- Lead intake and CSV import
- Deterministic lead scoring and client matching
- Outreach draft generation with human approval status
- Pipeline statuses: New, Qualified, Contacted, Follow-up, Converted, Not Fit
- Follow-up task queue with due dates
- Notes/history and audit logging
- File attachment metadata for leads
- Review response drafting workflow
- CSV exports for leads, tasks, and Google Sheets-ready data
- Daily report endpoint
- Basic health and metrics endpoints
- FastAPI Swagger/OpenAPI docs
- Render Free deployment with `render.yaml`

## Architecture

```mermaid
flowchart LR
    U[Admin / Manager / Agent] --> R[Render Free Web Service]
    R --> F[FastAPI App]
    F --> T[Jinja2 SaaS UI]
    F --> A[Role-Aware API Routes]
    F --> S[Services Layer]
    S --> DB[(SQLite MVP Database)]
    S --> E[CSV / Daily Report Exports]
    S --> N[Console Email Provider]
    S --> J[Local Background Job Registry]
    F --> H[/health and /metrics]
    G[GitHub main branch] --> R
```

## Deployment Architecture

NexusLead AI is deployed as a server-rendered FastAPI app on Render Free.

| Component | Current MVP implementation |
| --- | --- |
| Hosting | Render Free Web Service |
| URL | `https://nexuslead-ai.onrender.com` |
| Runtime | Python |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check | `/health` |
| UI | Jinja2 templates served by FastAPI |
| API docs | FastAPI Swagger/OpenAPI at `/docs` |
| Data store | SQLite file for MVP/demo use |
| CI/CD | GitHub Actions tests plus Render deploys from GitHub commits |
| Future DB path | PostgreSQL through Neon, Supabase, or Render PostgreSQL after migrations |

Render environment variables:

| Variable | Purpose |
| --- | --- |
| `NEXUSLEAD_SESSION_SECRET` | Signs login sessions |
| `NEXUSLEAD_UPLOAD_DIR` | Local upload metadata directory, defaults to `uploads` |
| `NEXUSLEAD_EMAIL_PROVIDER` | `console` for local/demo notification behavior |
| `PORT` | Provided by Render |
| `DATABASE_URL` | Future PostgreSQL connection string after migrations |

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://localhost:8000
```

Default local users are the same as the live demo credentials.

## Testing

```bash
python -m pytest
```

GitHub Actions runs the same test suite on push and pull request.

## Docker

```bash
docker compose up --build
```

Open `http://localhost:8000`.

## Deployment Instructions

Render is the primary deployment target for this server-rendered FastAPI MVP.

1. Push changes to `main`.
2. Render deploys from the GitHub repository.
3. Validate `render.yaml` if deployment settings change.
4. Confirm `https://nexuslead-ai.onrender.com/health` returns `status: ready`.
5. Confirm the public root URL serves the login UI.
6. Confirm Admin, Manager, and Agent demo accounts can access the dashboard.

## Data And Production Notes

The deployed MVP uses SQLite on Render's ephemeral filesystem. That is acceptable for a portfolio demo but not for durable production data. A production path should add:

- PostgreSQL with migrations, for example Neon, Supabase, or Render PostgreSQL
- Durable object storage for uploads
- Secret rotation and role administration policies
- Email provider integration such as SendGrid or AWS SES
- Calendar integration through Google Calendar or Microsoft Graph
- Observability with Prometheus/Grafana or a hosted monitoring tool

## Compliance Notes

Real integrations should use approved APIs, CRM imports, Google Sheets, manual entry, or authorized data sources. Outreach drafts must remain human-reviewed before use. This project does not include scraping bypasses, automated comment posting, or automated outbound sending.

## Additional Docs

- [Architecture](docs/architecture.md)
- [Deployment](docs/deployment.md)
- [Operations, jobs, email, calendar, monitoring, and migrations](docs/operations.md)
- [Google Sheets and n8n workflows](docs/n8n-expansion.md)
- [Compliance model](docs/compliance.md)
