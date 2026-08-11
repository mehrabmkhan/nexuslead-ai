# AWS Deployment

NexusLead AI is deployed on AWS with a low-cost EC2, Docker, Amazon ECR, PostgreSQL, CloudWatch, and GitHub Actions path in `ca-central-1`.

## Architecture

```text
User -> EC2 public HTTP endpoint -> Docker -> FastAPI container
FastAPI container -> PostgreSQL container on a named Docker volume
GitHub -> GitHub Actions -> Amazon ECR -> EC2 pull/restart cron
FastAPI container -> CloudWatch logs
```

See `diagrams/aws-architecture.mmd` for the Mermaid diagram.

## AWS Services

| Service | Purpose |
| --- | --- |
| Amazon ECR | Stores the NexusLead AI Docker image. |
| Amazon EC2 | Runs the single public Docker host. |
| PostgreSQL | Persistent application database running as a container with Docker volume `nexuslead-postgres`. |
| AWS CloudWatch | Runtime application logs, health, and workflow verification logs. |
| IAM | GitHub Actions OIDC role, ECR permissions, EC2 instance profile, and CloudWatch log permissions. |

## Recommended Low-Cost Setup

Current lowest-cost AWS-only production path:

- One `t3.micro` EC2 instance in `ca-central-1`.
- ECR private repository: `nexuslead-ai`.
- PostgreSQL in a Docker volume on the same EC2 host.
- 8 GB gp3 root disk.
- No NAT Gateway, no load balancer, no Elastic IP, and no managed RDS database.

RDS can create meaningful recurring charges, so the current deployment uses the local PostgreSQL container volume. For stronger durability later, move `DATABASE_URL` to a managed PostgreSQL service and reassess cost before enabling it.

## Production Environment Variables

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Yes | Current EC2 value points at `nexuslead-postgres` on the Docker network. |
| `POSTGRES_PASSWORD` | Yes | Generated once by EC2 bootstrap. |
| `NEXUSLEAD_SESSION_SECRET` | Yes | Generated once by EC2 bootstrap for signed sessions. |
| `NEXUSLEAD_UPLOAD_DIR` | No | Set to `/app/uploads`; use S3 for durable production uploads later. |
| `NEXUSLEAD_EMAIL_PROVIDER` | No | Defaults to `console`. |
| `LOG_LEVEL` | No | Defaults to `INFO`. |
| `PORT` | No | Container listens on `8000`; EC2 maps host port `80` to container port `8000`. |

## Manual Deployment Flow

1. Verify AWS identity:

   ```bash
   aws sts get-caller-identity
   ```

2. Create ECR:

   ```bash
   aws ecr create-repository --repository-name nexuslead-ai --image-scanning-configuration scanOnPush=true
   ```

3. Build locally:

   ```bash
   docker build -t nexuslead-ai:latest .
   ```

4. Authenticate Docker to ECR:

   ```bash
   aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
   ```

5. Tag and push:

   ```bash
   docker tag nexuslead-ai:latest <account-id>.dkr.ecr.<region>.amazonaws.com/nexuslead-ai:latest
   docker push <account-id>.dkr.ecr.<region>.amazonaws.com/nexuslead-ai:latest
   ```

6. Launch one EC2 instance with `scripts/aws/ec2-user-data.sh`:

   - Instance type: `t3.micro`
   - Region: `ca-central-1`
   - Public access: HTTP on TCP 80
   - Root disk: 8 GB gp3
   - IAM profile: `nexuslead-ec2-profile`
   - Security group: HTTP only, no SSH inbound

7. Confirm:

   ```bash
   curl http://<ec2-public-dns>/health
   ```

Current live URL:

```text
http://ec2-99-79-66-16.ca-central-1.compute.amazonaws.com
```

## CI/CD Flow

`.github/workflows/aws-deploy.yml` runs on pushes to `main`:

1. Install dependencies.
2. Run tests.
3. Authenticate to AWS using GitHub OIDC.
4. Build Docker image.
5. Push commit SHA and `latest` tags to ECR.
6. The EC2 cron job refreshes ECR auth, pulls `latest`, and restarts only the app container.

Required GitHub Secrets:

- `AWS_REGION`
- `AWS_GITHUB_ACTIONS_ROLE_ARN`

## Database Migrations

The Docker start command runs:

```bash
alembic upgrade head
```

when `DATABASE_URL` is configured, then starts Uvicorn. The first migration creates users, clients, leads, tasks, reviews, audit logs, and lead attachment metadata tables. PostgreSQL data persists in Docker volume `nexuslead-postgres`.

## Monitoring

Endpoints:

- `/health`: app and database health.
- `/metrics`: JSON operating metrics.
- `/docs`: OpenAPI UI.

Logs:

- Runtime logs: CloudWatch log group `/nexuslead-ai/ec2`, stream `nexuslead-ai`.
- Bootstrap and one-time smoke-test output: EC2 console output.

The app logs request method, path, status code, latency, and unhandled exceptions.

## Rollback

1. Find the previous image tag in ECR.
2. Retag it as `latest`, or update `/opt/nexuslead/deploy.sh` to pull the known-good immutable tag.
3. Wait for the EC2 deploy cron or run the deploy script through an approved remote execution path.
4. Confirm `/health`, login, dashboard, and exports.

## Remove Resources

To stop costs:

1. Terminate the EC2 instance.
2. Delete the ECR repository after images are no longer required.
3. Remove IAM roles and the EC2 instance profile created for deployment.
4. Remove CloudWatch log group `/nexuslead-ai/ec2` if retention cleanup is desired.

## Acceptance Checklist

Do not mark the AWS deployment complete until these pass against the EC2 URL or the EC2-side smoke test:

- `/`
- `/login`
- `/health`
- `/docs`
- Admin login
- Manager login
- Agent login
- Dashboard load
- Lead creation
- Client creation
- Task close
- Lead assignment
- Status update
- CSV export
- Data persistence after restart/redeploy
- Logout and login again
- Authenticated API access
