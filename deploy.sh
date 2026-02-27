#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}→${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

echo "========================================="
echo "  glyx-mcp Production Deployment"
echo "========================================="
echo ""

# Check for required commands
if ! command -v fly &> /dev/null; then
    print_error "flyctl is not installed. Install it with:"
    echo "  curl -L https://fly.io/install.sh | sh"
    exit 1
fi

print_success "flyctl found"

# Check if logged in
if ! fly auth whoami &> /dev/null; then
    print_error "Not logged in to Fly.io. Run: fly auth login"
    exit 1
fi

print_success "Authenticated with Fly.io"

# Check for .env.production
if [ ! -f .env.production ]; then
    print_warning ".env.production not found. Using .env if available..."
    if [ -f .env ]; then
        cp .env .env.production
        print_info "Copied .env to .env.production"
    else
        print_error "No environment file found. Create .env.production first."
        exit 1
    fi
fi

# Validate required environment variables
print_info "Validating environment variables..."

required_vars=(
    "OPENAI_API_KEY"
    "ANTHROPIC_API_KEY"
    "OPENROUTER_API_KEY"
)

source .env.production

missing_vars=()
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    print_error "Missing required environment variables:"
    for var in "${missing_vars[@]}"; do
        echo "  - $var"
    done
    exit 1
fi

print_success "Environment variables validated"

# Check JWT secret
if [ "$JWT_SECRET_KEY" == "CHANGE_ME_IN_PRODUCTION_USE_RANDOM_STRING" ]; then
    print_warning "JWT_SECRET_KEY not changed from default!"
    read -p "Generate a random JWT secret? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        JWT_SECRET_KEY=$(openssl rand -base64 32)
        print_success "Generated JWT_SECRET_KEY: $JWT_SECRET_KEY"
        echo "Add this to your .env.production file"
    fi
fi

# Set secrets on Fly.io
print_info "Setting secrets on Fly.io..."

fly secrets set \
    OPENAI_API_KEY="$OPENAI_API_KEY" \
    ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
    JWT_SECRET_KEY="$JWT_SECRET_KEY" \
    --app glyx-mcp

# Set optional secrets if provided
if [ -n "$CLAUDE_API_KEY" ]; then
    fly secrets set CLAUDE_API_KEY="$CLAUDE_API_KEY" --app glyx-mcp
fi

if [ -n "$MEM0_API_KEY" ]; then
    fly secrets set MEM0_API_KEY="$MEM0_API_KEY" --app glyx-mcp
fi

if [ -n "$LANGFUSE_SECRET_KEY" ]; then
    fly secrets set \
        LANGFUSE_SECRET_KEY="$LANGFUSE_SECRET_KEY" \
        LANGFUSE_PUBLIC_KEY="$LANGFUSE_PUBLIC_KEY" \
        LANGFUSE_HOST="$LANGFUSE_HOST" \
        --app glyx-mcp
fi

if [ -n "$SUPABASE_URL" ]; then
    fly secrets set \
        SUPABASE_URL="$SUPABASE_URL" \
        SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY" \
        SUPABASE_SERVICE_ROLE_KEY="$SUPABASE_SERVICE_ROLE_KEY" \
        --app glyx-mcp
fi

print_success "Secrets configured"

# Deploy
print_info "Deploying to Fly.io..."
fly deploy --app glyx-mcp

print_success "Deployment complete!"

echo ""
echo "========================================="
echo "  Deployment Summary"
echo "========================================="
echo ""
echo "App URL: https://glyx-mcp.fly.dev"
echo "MCP Endpoint: https://glyx-mcp.fly.dev/mcp"
echo "Health Check: https://glyx-mcp.fly.dev/api/healthz"
echo ""
echo "Next steps:"
echo "  1. Verify health: curl https://glyx-mcp.fly.dev/api/healthz"
echo "  2. Check logs: fly logs --app glyx-mcp"
echo "  3. Monitor status: fly status --app glyx-mcp"
echo ""
