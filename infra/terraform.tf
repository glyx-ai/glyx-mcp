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

  # Remote state in GCS (uncomment after initial setup)
  # backend "gcs" {
  #   bucket = "glyx-terraform-state"
  #   prefix = "glyx-mcp"
  # }
}

provider "google" {
  project     = var.project_id
  region      = var.region
  credentials = file("${path.module}/.gcp-key.json")
}

# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}
