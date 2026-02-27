#!/bin/bash
# =============================================================================
# Glyx MCP Server - Google Cloud Run Deployment Script
# =============================================================================
set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-glyx-ai}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="glyx-mcp"
IMAGE_NAME="us-central1-docker.pkg.dev/${PROJECT_ID}/glyx/${SERVICE_NAME}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse arguments
ACTION="${1:-deploy}"

case "$ACTION" in
    build)
        log_info "Building Docker image..."
        docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" --target production .
        log_info "Image built: ${IMAGE_NAME}:${IMAGE_TAG}"
        ;;

    push)
        log_info "Pushing image to Artifact Registry..."
        docker push "${IMAGE_NAME}:${IMAGE_TAG}"
        log_info "Image pushed successfully"
        ;;

    run)
        log_info "Deploying to Cloud Run..."
        gcloud run deploy "${SERVICE_NAME}" \
            --image "${IMAGE_NAME}:${IMAGE_TAG}" \
            --region "${REGION}" \
            --platform managed \
            --allow-unauthenticated \
            --port 8080 \
            --memory 1Gi \
            --cpu 1 \
            --min-instances 0 \
            --max-instances 10 \
            --timeout 300 \
            --set-env-vars "ENVIRONMENT=production"
        log_info "Deployment complete!"

        # Get service URL
        URL=$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format 'value(status.url)')
        log_info "Service URL: ${URL}"
        ;;

    deploy)
        log_info "Full deployment: build -> push -> run"
        $0 build
        $0 push
        $0 run
        ;;

    setup)
        log_info "Setting up GCP for deployment..."

        # Enable required APIs
        log_info "Enabling required APIs..."
        gcloud services enable artifactregistry.googleapis.com
        gcloud services enable run.googleapis.com
        gcloud services enable cloudbuild.googleapis.com

        # Create Artifact Registry repository
        log_info "Creating Artifact Registry repository..."
        gcloud artifacts repositories create glyx \
            --repository-format=docker \
            --location="${REGION}" \
            --description="Glyx container images" \
            || log_warn "Repository may already exist"

        # Configure Docker authentication
        log_info "Configuring Docker authentication..."
        gcloud auth configure-docker "${REGION}-docker.pkg.dev"

        log_info "Setup complete! You can now run: ./scripts/deploy.sh deploy"
        ;;

    logs)
        log_info "Fetching recent logs..."
        gcloud run services logs read "${SERVICE_NAME}" --region "${REGION}" --limit 100
        ;;

    status)
        log_info "Service status:"
        gcloud run services describe "${SERVICE_NAME}" --region "${REGION}"
        ;;

    *)
        echo "Usage: $0 {build|push|run|deploy|setup|logs|status}"
        echo ""
        echo "Commands:"
        echo "  build   - Build Docker image locally"
        echo "  push    - Push image to Artifact Registry"
        echo "  run     - Deploy image to Cloud Run"
        echo "  deploy  - Full deployment (build + push + run)"
        echo "  setup   - Initial GCP setup (APIs, registry, auth)"
        echo "  logs    - View recent service logs"
        echo "  status  - Show service status"
        exit 1
        ;;
esac
