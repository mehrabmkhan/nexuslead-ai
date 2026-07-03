# Architecture

NexusLead AI is a small FastAPI application backed by SQLite.

The demo flow is:

1. Seed synthetic client profiles.
2. Simulate public demand signals.
3. Score lead urgency and client fit.
4. Match each lead to the best client profile.
5. Draft outreach for human review.
6. Store the lead, task, review, and status records in SQLite.
7. Present the queue in a BPO agent dashboard.
8. Export CSVs and daily reports for operations review.

## Design Boundaries

The project intentionally avoids real scraping, automated commenting, and real personal data. Future integrations should use approved APIs, CRM imports, opt-in datasets, or manually approved sources.
