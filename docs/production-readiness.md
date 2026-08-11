# Production Readiness

NexusLead AI is frozen as a portfolio-grade internal SaaS MVP deployment. It is intentionally cost-conscious and avoids managed services that would add recurring cost without clear portfolio value.

## Live URLs

- Primary AWS HTTPS: `https://99-79-66-16.sslip.io`
- AWS HTTP fallback: `http://ec2-99-79-66-16.ca-central-1.compute.amazonaws.com`
- Render fallback: `https://nexuslead-ai.onrender.com`

The HTTPS hostname uses `sslip.io` because a trusted certificate cannot be issued for the raw AWS `compute.amazonaws.com` hostname. If the EC2 public IP changes, update the workflow HTTPS domain.

## AWS Inventory

| Resource | Current value |
| --- | --- |
| Region | `ca-central-1` |
| EC2 | `i-0ff17fb92d002e391` |
| Instance type | `t3.micro` |
| Public IP | `99.79.66.16` |
| EBS | 8 GB gp3 root volume |
| ECR | `nexuslead-ai` |
| CloudWatch | `/nexuslead-ai/ec2` |
| Security group | HTTP 80 and HTTPS 443 only |
| IAM EC2 role | `nexuslead-ec2-role` |
| IAM GitHub role | `nexuslead-github-actions-role` |

No NAT Gateway, load balancer, Elastic IP, RDS instance, snapshots, unattached volumes, or multi-instance resources are used.

## Security Posture

- GitHub Actions uses OIDC, not long-lived AWS access keys.
- OIDC trust is scoped to `mehrabmkhan/nexuslead-ai` on `refs/heads/main`.
- The GitHub role can push to the NexusLead ECR repository and send SSM commands only to the NexusLead EC2 instance.
- EC2 administration uses SSM; SSH is not open publicly.
- PostgreSQL and Docker daemon are not exposed publicly.
- Caddy terminates HTTPS and proxies internally to the FastAPI container.
- Secure cookies are enabled on EC2 with `NEXUSLEAD_SECURE_COOKIES=true`.

## Deployment

Pushes to `main` run:

1. Tests.
2. OIDC authentication to AWS.
3. Multi-architecture Docker image build.
4. Push to ECR.
5. SSM command to EC2.
6. Candidate container startup and health check.
7. Promotion of the healthy app container.
8. HTTPS `/health` verification.

Manual live acceptance can be run from the `aws-deploy` workflow with `run_live_acceptance=true`. It creates verification records, so it is not run on every push.

## Monitoring

- Runtime logs go to CloudWatch log group `/nexuslead-ai/ec2`.
- Retention is 14 days.
- `/health`, `/metrics`, and `/docs` remain available.

Recommended no-surprise monitoring additions:

- AWS Budget at `$5/month`.
- Free Tier or zero-spend alert.
- Manual monthly check of EC2 status checks, root disk usage, and CloudWatch errors.

## Backups

The EC2 deploy script installs:

```bash
/opt/nexuslead/backup-postgres.sh
```

It runs daily from `/etc/cron.d/nexuslead-backup`, writes compressed dumps to `/opt/nexuslead/backups`, and deletes dumps older than seven days.

Restore command:

```bash
gzip -dc /opt/nexuslead/backups/nexuslead-<timestamp>.sql.gz | docker exec -i nexuslead-postgres psql -U nexuslead -d nexuslead
```

## Cost Posture

The deployment is intentionally small, but a continuously running EC2 instance with a public IPv4 address is not guaranteed to stay below `$5/month` outside AWS credits or Free Tier benefits.

Expected low-traffic monthly cost outside credits:

- EC2 `t3.micro`: roughly `$8-10/month` depending on regional on-demand pricing.
- Public IPv4: roughly `$3.60/month`.
- 8 GB gp3 EBS: under `$1/month`.
- ECR and CloudWatch: usually pennies at this scale.

To reduce cost below that, stop the EC2 instance when not being reviewed, use Render free tier as the public demo fallback, or replace the always-on EC2 host with a free/credit-backed environment. Do not add NAT Gateway, load balancer, RDS, or Elastic IP unless the cost is intentionally accepted.

## Stop All AWS Charges

To stop all NexusLead AI AWS charges later:

1. Terminate EC2 instance `i-0ff17fb92d002e391`.
2. Delete ECR repository `nexuslead-ai`.
3. Delete CloudWatch log group `/nexuslead-ai/ec2`.
4. Delete IAM roles `nexuslead-ec2-role` and `nexuslead-github-actions-role`.
5. Delete instance profile `nexuslead-ec2-profile`.
6. Delete security group `sg-039f27e6aaf629c52` after the instance is gone.
7. Remove the GitHub OIDC provider if no other repository uses it.

## Remaining Limitations

- The HTTPS hostname depends on the current public IP because no custom domain was purchased.
- PostgreSQL backups live on the same EC2 root volume; copy them elsewhere before treating this as production.
- There is no high availability, managed database, WAF, or load balancer by design.
- Public IPv4 cost makes the always-on AWS deployment exceed the strict `$0-5/month` target outside credits.
