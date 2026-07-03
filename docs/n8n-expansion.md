# n8n Expansion Plan

NexusLead AI can later connect to n8n without changing the compliance model.

## Future Workflow Ideas

### CRM Import

Import approved lead or client CSV exports from a CRM. The workflow should validate columns, remove duplicates, and mark imported records as approved-source data.

### Email Draft Approval

Send drafted outreach to a manager approval queue. n8n can notify the assigned employee, but the final send should remain manual or approval-gated.

### Slack or Teams Alerts

Post high-priority lead alerts to a private team channel. Alerts should include the lead context, matched client, score, and dashboard link.

### Google Sheets Export

Export lead and task queues to a shared operations sheet for teams that still manage daily work in spreadsheets.

### Scheduled Lead Checks

Use approved APIs, CRM imports, opt-in sources, or manually approved data feeds. Do not scrape real websites or bypass platform limits.

### Review Monitoring

Connect to approved review APIs or client-provided exports. Negative reviews should create review tasks for employees, not automated public replies.

## Guardrails

- No scraping.
- No automated commenting.
- No real personal data unless the source is approved and compliant.
- No message sending without human approval.
