# =============================================================================
# Glyx MCP Server - Makefile
# =============================================================================

.PHONY: help dev server test lint deploy infra-init infra-plan infra-apply

# Default target
help:
	@echo "Glyx MCP Server - Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make dev          - Start development server with Docker Compose"
	@echo "  make server       - Run server locally with uvicorn"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Check code with ruff"
	@echo "  make lint-fix     - Fix code issues with ruff"
	@echo ""
	@echo "Infrastructure (Terraform):"
	@echo "  make infra-init   - Initialize Terraform"
	@echo "  make infra-plan   - Preview infrastructure changes"
	@echo "  make infra-apply  - Apply infrastructure changes"
	@echo "  make infra-output - Show Terraform outputs"
	@echo ""
	@echo "Deployment:"
	@echo "  make deploy-build - Build Docker image for production"
	@echo "  make deploy-push  - Push image to Artifact Registry"
	@echo "  make deploy       - Full deployment (infra + image)"
	@echo ""

# =============================================================================
# Development
# =============================================================================

dev:
	docker compose up

dev-build:
	docker compose up --build

server:
	uv run uvicorn api.server:combined_app --host 0.0.0.0 --port 8080 --reload

# =============================================================================
# Testing & Linting
# =============================================================================

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ -v --cov=glyx_mcp --cov=api

lint:
	uv run ruff check . && uv run ruff format --check .

lint-fix:
	uv run ruff check --fix . && uv run ruff format .

# =============================================================================
# Infrastructure (Terraform)
# =============================================================================

infra-init:
	cd infra && terraform init

infra-plan:
	cd infra && terraform plan

infra-apply:
	cd infra && terraform apply

infra-destroy:
	cd infra && terraform destroy

infra-output:
	cd infra && terraform output

# =============================================================================
# Deployment
# =============================================================================

# Get image URL from Terraform output
IMAGE_URL := $(shell cd infra && terraform output -raw image_url 2>/dev/null || echo "us-central1-docker.pkg.dev/PROJECT_ID/glyx/glyx-mcp")

deploy-build:
	docker build -t $(IMAGE_URL):latest --target production .

deploy-push:
	docker push $(IMAGE_URL):latest

deploy-image: deploy-build deploy-push

deploy: infra-apply
	@echo "Infrastructure deployed! Service URL:"
	@cd infra && terraform output service_url

# Full deployment: build image, push, and apply Terraform
deploy-full: deploy-image deploy
