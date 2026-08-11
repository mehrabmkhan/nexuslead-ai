# Operations Notes

NexusLead AI is an internal B2B lead operations platform for NextRNS-style BPO teams. This document keeps the future-ready operational pieces explicit without requiring heavy infrastructure for local development.

## Roles

- Admin: users, clients, leads, exports, analytics, background job readiness, audit review.
- Manager: lead review, outreach draft approval, agent assignment, analytics review.
- Agent: lead creation, status updates, notes, attachments, and assigned task export.

## Database And Migrations

Local development uses SQLite and startup table initialization in `app/database.py`. AWS production uses PostgreSQL through `DATABASE_URL`.

Alembic is included for production schema management:

```bash
alembic upgrade head
```

The Docker start script runs migrations automatically when `DATABASE_URL` is set, then starts Uvicorn. The app keeps SQLite as the no-friction local backend and uses a psycopg adapter for PostgreSQL deployments.

## Background Jobs

`app/background.py` defines a lightweight job registry for:

- scheduled lead checks
- daily reports
- task reminders

Local development does not require Redis. `/jobs/status` shows registered jobs and readiness. A future Celery migration can map each function to a Celery task and schedule them with Celery Beat.

Optional future environment variables:

- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`

## Email Notifications

`app/notifications.py` uses a console provider locally. Future providers can implement the same `send` shape for:

- SendGrid
- AWS SES
- Microsoft Graph mail
- Google Workspace mail

Recommended production rules:

- keep outreach human-reviewed before sending
- log approval actions
- send only through approved channels and authorized integrations
- store provider message IDs in an audit table if outbound delivery is added

## Calendar And Task Integration

Tasks include due dates and can be exported through `/export/tasks.csv`. Future calendar integration should use authorized APIs:

- Google Calendar API
- Microsoft Graph Calendar API
- approved CRM task integrations

A safe first step is a one-way export from approved tasks into calendar events after manager approval.

## File Attachments

The app stores local files under `uploads/` and records metadata in `lead_attachments`. The folder is ignored by git. Production deployments should use object storage such as S3, Cloudflare R2, or Azure Blob Storage and store only metadata in the database.

## Monitoring

Endpoints:

- `/health`: app and database mode
- `/metrics`: simple JSON metrics
- `/jobs/status`: background job readiness for admins

For Prometheus/Grafana, add `prometheus-fastapi-instrumentator` or expose text-format metrics from `/metrics`. Keep alerting focused on uptime, error rate, task backlog, and export/job failures.

## Compliance

Real integrations should use approved APIs, CRM imports, Google Sheets, manual entry, or authorized data sources. Do not add automated comment posting, ban-evasion, scraping bypasses, or automated outreach sending. Outreach drafts must remain human-reviewed before use.
