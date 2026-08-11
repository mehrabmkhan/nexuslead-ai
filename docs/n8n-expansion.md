# n8n and Google Sheets Workflows

NexusLead AI currently supports a token-protected webhook suitable for n8n and a Google Sheets-compatible CSV workflow. Direct third-party account connections are future integrations and should only be enabled through approved APIs and human approval workflows.

## Operational Now

### n8n Webhook Lead Intake

Use an n8n HTTP Request node to send approved lead data to:

```text
POST /webhooks/n8n/leads
Authorization: Bearer <NEXUSLEAD_WEBHOOK_TOKEN>
Content-Type: application/json
```

Required JSON fields:

```json
{
  "source": "n8n webhook",
  "category": "Security company",
  "city": "Mississauga",
  "context": "Warehouse manager needs urgent overnight coverage this week",
  "budget": 9000,
  "owner": "Unassigned",
  "due_date": "2026-08-20"
}
```

The endpoint validates required fields, rejects duplicates, classifies priority, recommends a client, creates an outreach draft, writes timeline/audit events, and opens a follow-up task.

### Google Sheets CSV Workflow

1. Download `/templates/google-sheets-leads.csv`.
2. Fill rows in Google Sheets using the required columns.
3. Export the sheet as CSV.
4. Upload the file in the dashboard CSV import panel.
5. Review the import history for created, duplicate, and error counts.
6. Export updated leads through `/export/google-sheets.csv`.

## Future Workflow Ideas

### CRM Import

Import approved lead or client CSV exports from a CRM or use official CRM APIs. The workflow should validate columns, remove duplicates, and mark imported records as approved-source data.

### Email Draft Approval

Send drafted outreach to a manager approval queue. n8n can notify the assigned employee, but the final send should remain manual or approval-gated.

### Slack or Teams Alerts

Post high-priority lead alerts to a private team channel. Alerts should include the lead context, matched client, score, and dashboard link.

### Google Sheets Export

Direct Sheets API sync can be added after an approved Google Cloud project and credential model exists. Until then, use the CSV template/export workflow.

### Scheduled Lead Checks

Use approved APIs, CRM imports, opt-in sources, or manually approved data feeds. Do not scrape real websites or bypass platform limits.

### Review Monitoring

Connect to approved review APIs or client-provided exports. Negative reviews should create review tasks for employees, not automated public replies.

## Guardrails

- No scraping.
- No automated commenting.
- No real personal data unless the source is approved and compliant.
- No message sending without human approval.
