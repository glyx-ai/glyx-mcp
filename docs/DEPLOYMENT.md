# Deployment Guide

This guide covers deploying glyx-mcp to production environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Configuration](#environment-configuration)
- [Deployment Options](#deployment-options)
  - [Fly.io (Recommended)](#flyio-recommended)
  - [Docker Compose](#docker-compose)
  - [Google Cloud Run](#google-cloud-run)
- [Health Checks & Monitoring](#health-checks--monitoring)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Python 3.11 or higher
- Docker and Docker Compose (for containerized deployment)
- `flyctl` CLI (for Fly.io deployment)
- API keys for:
  - OpenAI (GPT models)
  - Anthropic (Claude models)
  - OpenRouter (Grok and other models)

---

## Environment Configuration

### 1. Create Production Environment File

Copy the production template and fill in your values:

```bash
cp .env.production .env.production.local
```

Edit `.env.production.local` and set **all required variables**:

```bash
# Required API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...

# JWT Secret (MUST change in production!)
JWT_SECRET_KEY=your-random-secret-here
```

### 2. Generate Secure JWT Secret

```bash
openssl rand -base64 32
```

Update `JWT_SECRET_KEY` in your environment file with this value.

### 3. Optional Integrations

Configure these if you're using the features:

**Langfuse Tracing:**
```bash
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

**Supabase (Auth/Database):**
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...

# Daemon Service User (for backend operations - see Daemon Authentication below)
DAEMON_USER_EMAIL=daemon@glyx.ai
DAEMON_USER_PASSWORD=your-secure-password
```

**GitHub App (Webhooks):**
```bash
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n..."
GITHUB_WEBHOOK_SECRET=your-webhook-secret
```

---

## Deployment Options

### Fly.io (Recommended)

Fly.io provides automatic scaling, global edge deployment, and built-in SSL.

#### Initial Setup

1. **Install flyctl:**
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login:**
   ```bash
   fly auth login
   ```

3. **Create app (first time only):**
   ```bash
   fly apps create glyx-mcp
   ```

#### Deploy

Use the automated deployment script:

```bash
./deploy.sh
```

This script will:
- Validate environment variables
- Set secrets on Fly.io
- Deploy the application
- Run health checks

#### Manual Deployment

If you prefer manual control:

```bash
# Set secrets
fly secrets set \
  OPENAI_API_KEY="sk-..." \
  ANTHROPIC_API_KEY="sk-ant-..." \
  OPENROUTER_API_KEY="sk-or-..." \
  JWT_SECRET_KEY="your-secret" \
  --app glyx-mcp

# Deploy
fly deploy --app glyx-mcp
```

#### Verify Deployment

```bash
# Check status
fly status --app glyx-mcp

# View logs
fly logs --app glyx-mcp

# Test health endpoint
curl https://glyx-mcp.fly.dev/api/healthz
```

#### MCP Client Configuration

Configure your MCP client (Claude Desktop, etc.) to use the deployed service:

```json
{
  "mcpServers": {
    "glyx-mcp": {
      "transport": {
        "type": "http",
        "url": "https://glyx-mcp.fly.dev/mcp"
      }
    }
  }
}
```

---

### Docker Compose

For local development or self-hosted production:

#### 1. Build and Start

```bash
# Build the image
docker compose build

# Start the service
docker compose up -d
```

#### 2. View Logs

```bash
docker compose logs -f glyx-mcp
```

#### 3. Stop Service

```bash
docker compose down
```

#### Production Docker Compose

For production, use the production build target:

```yaml
# compose.production.yml
services:
  glyx-mcp:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
    env_file:
      - .env.production
    ports:
      - "8080:8080"
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
```

Run with:
```bash
docker compose -f compose.production.yml up -d
```

---

### Google Cloud Run (Production)

The production deployment uses **Terraform + GitHub Actions** for infrastructure-as-code CI/CD.

#### Architecture

```
GitHub (main branch)
    ↓ push triggers workflow
GitHub Actions
    ├── Build Docker image → Artifact Registry
    └── Terraform Apply → Cloud Run service
            ├── Secrets from Secret Manager
            └── IAM via Workload Identity Federation
```

**Live endpoint:** `https://glyx-mcp-996426597393.us-central1.run.app`

#### CI/CD Pipeline

Pushing to `main` automatically:
1. Builds Docker image with commit SHA tag
2. Pushes to Artifact Registry (`us-central1-docker.pkg.dev/cs-poc-fu4tioc8i2w4ev3epp69dm3/glyx`)
3. Runs `terraform apply` to update Cloud Run service
4. Deploys new revision with zero downtime

#### Infrastructure (Terraform)

All infrastructure is managed in `/infra`:

```
infra/
├── terraform.tf      # Provider config, GCS backend
├── main.tf           # Resources (Cloud Run, Secrets, IAM)
├── variables.tf      # Input variables
├── outputs.tf        # Service URLs
└── locals.tf         # Computed values
```

**Resources managed by Terraform:**
- Artifact Registry repository
- Secret Manager secrets (11 secrets)
- Cloud Run v2 service
- Service account with secret access
- Public invoker IAM binding

**Resources managed outside Terraform (via GCP Console):**
- Workload Identity Federation pool/provider
- GitHub Actions service account
- Project-level IAM bindings
- GCP APIs (already enabled)

#### GitHub Actions Service Account

The `github-actions@cs-poc-fu4tioc8i2w4ev3epp69dm3.iam.gserviceaccount.com` SA requires:

| Role | Purpose |
|------|---------|
| `roles/run.admin` | Deploy Cloud Run services |
| `roles/artifactregistry.admin` | Push images, manage IAM |
| `roles/secretmanager.admin` | Manage secrets |
| `roles/iam.serviceAccountUser` | Act as Cloud Run SA |
| `roles/iam.serviceAccountViewer` | Read SA metadata |
| `roles/storage.objectAdmin` | Terraform state in GCS |

#### GitHub Secrets Required

Set these in GitHub repo settings → Secrets:

| Secret | Description |
|--------|-------------|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | WIF provider name |
| `GCP_SERVICE_ACCOUNT` | GitHub Actions SA email |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | (Deprecated) Supabase service role key |
| `DAEMON_USER_EMAIL` | Daemon service user email (see below) |
| `DAEMON_USER_PASSWORD` | Daemon service user password |
| `MEM0_API_KEY` | Mem0 API key |
| `LOGFIRE_TOKEN` | Logfire observability token |
| `KNOCK_API_KEY` | Knock notifications API key |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key |

#### Manual Deployment

To deploy manually (e.g., from local machine):

```bash
cd infra

# Initialize Terraform
terraform init

# Plan changes
terraform plan \
  -var="project_id=cs-poc-fu4tioc8i2w4ev3epp69dm3" \
  -var="anthropic_api_key=$ANTHROPIC_API_KEY" \
  # ... other vars

# Apply
terraform apply
```

#### Troubleshooting CI/CD

**Terraform state lock:**
```bash
# If workflow cancelled mid-apply, delete lock file:
gsutil rm gs://glyx-terraform-state/glyx-mcp/default.tflock
```

**Permission denied errors:**
```bash
# Add missing role to GitHub Actions SA:
gcloud projects add-iam-policy-binding cs-poc-fu4tioc8i2w4ev3epp69dm3 \
  --member="serviceAccount:github-actions@cs-poc-fu4tioc8i2w4ev3epp69dm3.iam.gserviceaccount.com" \
  --role="roles/MISSING_ROLE" \
  --condition=None
```

**View deployment logs:**
```bash
gh run view <run-id> --log
```

#### Verify Deployment

```bash
# Check API version
curl -s https://glyx-mcp-996426597393.us-central1.run.app/openapi.json | jq '.info.version'

# Check health
curl https://glyx-mcp-996426597393.us-central1.run.app/health

# View API docs
open https://glyx-mcp-996426597393.us-central1.run.app/docs
```

---

## Health Checks & Monitoring

### Health Endpoints

The application provides multiple health check endpoints:

#### Basic Health Check
```bash
curl https://your-domain.com/api/healthz
```

Response:
```json
{
  "status": "ok",
  "timestamp": "2025-12-04T10:30:00Z",
  "service": "glyx-mcp"
}
```

#### Detailed Health Check
```bash
curl https://your-domain.com/api/health/detailed
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2025-12-04T10:30:00Z",
  "service": "glyx-mcp",
  "checks": {
    "supabase": {"status": "ok", "message": "Connected"},
    "langfuse": {"status": "ok", "message": "Connected"},
    "openai": {"status": "configured"},
    "anthropic": {"status": "configured"},
    "openrouter": {"status": "configured"}
  }
}
```

#### Metrics Endpoint
```bash
curl https://your-domain.com/api/metrics
```

Response:
```json
{
  "timestamp": "2025-12-04T10:30:00Z",
  "service": "glyx-mcp",
  "uptime_seconds": 3600.5,
  "agents_available": 11
}
```

### Monitoring Setup

#### Fly.io Monitoring

```bash
# View metrics dashboard
fly dashboard glyx-mcp

# Set up alerts
fly alerts create --name "high-cpu" --metric "cpu_usage" --threshold 80
```

#### Custom Monitoring

Configure external monitoring tools (Datadog, New Relic, etc.) to poll:
- `/api/healthz` - Basic uptime
- `/api/health/detailed` - Component status
- `/api/metrics` - Performance metrics

---

## Security Considerations

### 1. API Keys

**Never commit API keys to version control!**

- Use `.env.production` (gitignored)
- Use secrets management in production (Fly.io secrets, Cloud Run secrets, etc.)
- Rotate keys regularly

### 2. JWT Secret

**Critical:** Change `JWT_SECRET_KEY` from default in production:

```bash
# Generate strong secret
openssl rand -base64 32

# Set in environment
export JWT_SECRET_KEY="your-generated-secret"
```

### 3. CORS Configuration

The server allows CORS for:
- `http://localhost:3000` (development)
- `http://127.0.0.1:3000`
- Chrome extensions (`chrome-extension://...`)

For production, update CORS settings in `src/glyx/mcp/server.py`:

```python
combined_app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-production-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 4. Rate Limiting

Consider adding rate limiting for production:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
api_app.state.limiter = limiter
api_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

### 5. HTTPS Only

Always use HTTPS in production:
- Fly.io: Automatic HTTPS
- Cloud Run: Automatic HTTPS
- Self-hosted: Use reverse proxy (nginx, Caddy) with SSL

### 6. Daemon Authentication

The backend API uses a **dedicated service user** for database operations rather than a service role key that bypasses RLS. This ensures proper Row Level Security enforcement.

#### Why Not Service Role Keys?

Supabase offers service role keys (`eyJ...` JWT format) that bypass all RLS policies. While convenient, this is an anti-pattern:

- **Security risk**: Any code with the key can access/modify all data
- **No audit trail**: RLS policies provide clear access rules
- **Deprecated pattern**: Supabase is moving toward explicit authentication

#### Setup

1. **Create the daemon user in Supabase:**

   Go to Supabase Dashboard → Authentication → Users → Add User:
   - Email: `daemon@glyx.ai`
   - Password: Generate a strong password (32+ chars)
   - Check "Auto Confirm User"

2. **Apply RLS migration:**

   ```bash
   supabase db push
   # Or run supabase/migrations/20260215_daemon_user_rls.sql via SQL Editor
   ```

3. **Set environment variables:**

   ```bash
   DAEMON_USER_EMAIL=daemon@glyx.ai
   DAEMON_USER_PASSWORD=your-secure-password
   ```

4. **Add GitHub secrets** (for CI/CD):
   - `DAEMON_USER_EMAIL`
   - `DAEMON_USER_PASSWORD`

#### How It Works

The backend authenticates as the daemon user via Supabase Auth:

```python
client = create_client(url, anon_key)
client.auth.sign_in_with_password({
    "email": settings.daemon_user_email,
    "password": settings.daemon_user_password,
})
```

RLS policies grant the daemon user access to all agent tasks:

```sql
CREATE POLICY "Daemon can update all tasks" ON agent_tasks
FOR UPDATE USING (
    auth.jwt() ->> 'email' = 'daemon@glyx.ai'
);
```

This provides:
- **Proper RLS enforcement** for all other users
- **Explicit, auditable access** for backend operations
- **Standard Supabase auth flow** (no special key types)

---

## Troubleshooting

### Deployment Fails

**Check logs:**
```bash
# Fly.io
fly logs --app glyx-mcp

# Docker Compose
docker compose logs glyx-mcp

# Cloud Run
gcloud run services logs read glyx-mcp
```

**Common issues:**

1. **Missing API keys:**
   - Verify all required keys are set
   - Check `/api/health/detailed` for configuration status

2. **Health check fails:**
   - Ensure port 8080 is accessible
   - Check if server is starting correctly

3. **Memory issues:**
   - Increase memory allocation (Fly.io: edit `fly.toml`, Cloud Run: `--memory 2Gi`)

### Agent Execution Fails

**Check agent availability:**
```bash
curl https://your-domain.com/api/agents
```

**Verify CLI tools are installed:**
```bash
# SSH into container (Fly.io)
fly ssh console --app glyx-mcp

# Check installations
aider --version
opencode --version
cursor-agent --version
```

### Performance Issues

1. **Monitor metrics:**
   ```bash
   curl https://your-domain.com/api/metrics
   ```

2. **Check resource usage:**
   ```bash
   fly status --app glyx-mcp
   ```

3. **Scale if needed:**
   ```bash
   fly scale count 2 --app glyx-mcp
   fly scale vm shared-cpu-2x --app glyx-mcp
   ```

---

## Production Checklist

Before going to production, verify:

- [ ] All required API keys are set
- [ ] JWT secret changed from default
- [ ] CORS configured for production domains
- [ ] Health checks passing (`/api/healthz`)
- [ ] Monitoring set up (alerts, logs)
- [ ] SSL/HTTPS enabled
- [ ] Backups configured (if using database)
- [ ] Rate limiting enabled (optional but recommended)
- [ ] Error tracking set up (Sentry, etc.)
- [ ] Documentation updated with production URLs

---

## Support

For issues or questions:
- GitHub Issues: [glyx-mcp/issues](https://github.com/yourusername/glyx-mcp/issues)
- Documentation: [docs/](../docs/)
- MCP Protocol: [modelcontextprotocol.io](https://modelcontextprotocol.io)
