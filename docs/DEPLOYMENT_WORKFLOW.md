# Deployment and Local Dev Workflow

This project now uses a script-first Docker workflow that supports:

- one-command local stack startup
- reproducible image builds
- ECR publishing
- ECS service rollouts
- EC2 Docker Compose refresh

## 1) Local Development (Fast Path)

From repo root:

- `scripts/stack up` (full stack, including credential-free worker and credential-bearing harness runtimes)
- `scripts/stack smoke` (health checks)
- `scripts/stack logs backend` (tail specific logs)
- `STACK_LOG_FOLLOW=0 scripts/stack logs backend` (non-following snapshot for CI/debug)
- `scripts/stack down` (stop everything)

Default local ports:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:18000`
- LangGraph service: `http://localhost:8080`
- Postgres: `localhost:15432`
- Redis: `localhost:16379`
- DynamoDB Local: `localhost:18001`

For frontend hot-reload while keeping containerized backend/langgraph:

- `scripts/stack up-core`
- `scripts/stack frontend-dev`
- `STACK_FRONTEND_DEV_DRY_RUN=1 scripts/stack frontend-dev` (command preview only)

## 2) Image Build and Publish to AWS ECR

Requirements:

- Docker
- AWS CLI with permissions for ECR + STS

Publish all runtime images:

- `AWS_REGION=us-east-1 IMAGE_TAG=<tag> scripts/publish-ecr`
- `DRY_RUN=1 AWS_ACCOUNT_ID=<account> IMAGE_TAG=<tag> scripts/publish-ecr` (safe command preview)

Optional env vars:

- `AWS_ACCOUNT_ID` (auto-detected when omitted)
- `ECR_REPO_PREFIX` (default `ai-multiplayer-chat`)

The script creates repositories if missing and publishes:

- `<account>.dkr.ecr.<region>.amazonaws.com/ai-multiplayer-chat/backend:<tag>`
- `<account>.dkr.ecr.<region>.amazonaws.com/ai-multiplayer-chat/langgraph-service:<tag>`
- `<account>.dkr.ecr.<region>.amazonaws.com/ai-multiplayer-chat/frontend:<tag>`
- `<account>.dkr.ecr.<region>.amazonaws.com/ai-multiplayer-chat/worker-runtime:<tag>`

## 3) ECS Rollout (after task definitions reference new tag)

Trigger rolling deployments:

- `ECS_CLUSTER=<cluster> ECS_BACKEND_SERVICE=<svc> ECS_LANGGRAPH_SERVICE=<svc> ECS_FRONTEND_SERVICE=<svc> ECS_WORKER_RUNTIME_SERVICE=<svc> ECS_CODEX_RUNTIME_SERVICE=<svc> ECS_CLAUDE_RUNTIME_SERVICE=<svc> ECS_OPENCODE_RUNTIME_SERVICE=<svc> ECS_PI_RUNTIME_SERVICE=<svc> scripts/deploy-ecs`
- `DRY_RUN=1 ECS_CLUSTER=<cluster> ECS_BACKEND_SERVICE=<svc> scripts/deploy-ecs` (safe command preview)

At least one service variable must be provided.

## 4) EC2 Compose Refresh (optional path)

If running Docker Compose on EC2:

- `EC2_HOST=<host> EC2_USER=ec2-user EC2_APP_DIR=/opt/ai-multiplayer-chat scripts/deploy-ec2-compose`
- `DRY_RUN=1 EC2_HOST=<host> scripts/deploy-ec2-compose` (safe command preview)

This runs `./scripts/stack up` on the remote host.

## 5) Repo-root Artifact Prevention

A guard script now blocks accidental untracked repo-root files:

- `scripts/check-repo-hygiene`

`scripts/stack up` and `scripts/stack up-core` invoke this automatically.

Why this exists:

- shell commands with unquoted text containing redirection symbols (`>`, `->`) can accidentally create root files.
- using `--body-file` for long CLI text payloads avoids this issue.

## 6) Architecture Notes for AWS

Recommended production architecture:

- ECS/Fargate or ECS/EC2 tasks for:
  - frontend container
  - backend container
  - langgraph-service container
  - credential-free worker-runtime container
  - four provider runtime containers using the same image, each with one adapter allowlist and one auth volume
- Managed stores:
  - DynamoDB for application/session metadata and workflow mapping
  - RDS Postgres for thread/run history
  - ElastiCache Redis for runtime signaling/cache
  - EFS for the Compose-equivalent shared demo workspace, or preferably S3 plus disposable per-job workspaces/artifacts

For production, replace local endpoints in env vars:

- backend: `BACKEND_DYNAMODB_ENDPOINT_URL` should target AWS DynamoDB (or be unset)
- langgraph: `LANGGRAPH_POSTGRES_DSN`, `LANGGRAPH_REDIS_URL` should target RDS/ElastiCache
- runtime services: use one disposable task per assignment in production; do not carry personal subscription credentials into a shared multi-user service
- do not deploy the worker/provider services as independent ECS filesystems and expect Compose named-volume sharing; provision EFS or externalize workspaces and artifacts first
