# Cleanup

Local development does not create cloud infrastructure. AWS resources created for a live deployment must be removed separately; see `docs/aws-deployment.md`.

Local development data is stored in SQLite. Remove it with:

```bash
del data\nexuslead.db
```

Generated reports and CSV exports under `reports/` can also be removed.
