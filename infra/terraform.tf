# =============================================================================
# Terraform Configuration - Glyx MCP Server
# =============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }

  backend "gcs" {
    bucket = "glyx-terraform-state"
    prefix = "glyx-mcp"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  # Uses Application Default Credentials (ADC)
  # - Local: gcloud auth application-default login
  # - CI: Workload Identity Federation
}

# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "iamcredentials.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}
