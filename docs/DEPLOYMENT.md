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
SUPABASE_SERVICE_ROLE_KEY=eyJ...
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

### Google Cloud Run

Deploy to Google Cloud Run for serverless scaling:

#### 1. Build and Push Container

```bash
# Build for Cloud Run
gcloud builds submit --tag gcr.io/YOUR-PROJECT-ID/glyx-mcp

# Or use Docker:
docker build -t gcr.io/YOUR-PROJECT-ID/glyx-mcp .
docker push gcr.io/YOUR-PROJECT-ID/glyx-mcp
```

#### 2. Deploy to Cloud Run

```bash
gcloud run deploy glyx-mcp \
  --image gcr.io/YOUR-PROJECT-ID/glyx-mcp \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars OPENAI_API_KEY=sk-...,ANTHROPIC_API_KEY=sk-ant-... \
  --memory 1Gi \
  --cpu 1
```

#### 3. Set Secrets (Secure Alternative)

```bash
# Create secrets
echo -n "sk-..." | gcloud secrets create openai-api-key --data-file=-

# Deploy with secrets
gcloud run deploy glyx-mcp \
  --image gcr.io/YOUR-PROJECT-ID/glyx-mcp \
  --update-secrets OPENAI_API_KEY=openai-api-key:latest
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
