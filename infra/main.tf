# =============================================================================
# Glyx MCP Server - Google Cloud Infrastructure
# =============================================================================

# -----------------------------------------------------------------------------
# Artifact Registry - Container image storage
# -----------------------------------------------------------------------------

resource "google_artifact_registry_repository" "glyx" {
  location      = var.region
  repository_id = "glyx"
  description   = "Glyx container images"
  format        = "DOCKER"

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

# -----------------------------------------------------------------------------
# Secret Manager - Secure storage for API keys
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "anthropic-api-key"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "anthropic_api_key" {
  secret      = google_secret_manager_secret.anthropic_api_key.id
  secret_data = var.anthropic_api_key
}

resource "google_secret_manager_secret" "openai_api_key" {
  secret_id = "openai-api-key"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "openai_api_key" {
  secret      = google_secret_manager_secret.openai_api_key.id
  secret_data = var.openai_api_key
}

resource "google_secret_manager_secret" "openrouter_api_key" {
  secret_id = "openrouter-api-key"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "openrouter_api_key" {
  secret      = google_secret_manager_secret.openrouter_api_key.id
  secret_data = var.openrouter_api_key
}

resource "google_secret_manager_secret" "supabase_url" {
  secret_id = "supabase-url"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "supabase_url" {
  secret      = google_secret_manager_secret.supabase_url.id
  secret_data = var.supabase_url
}

resource "google_secret_manager_secret" "supabase_anon_key" {
  secret_id = "supabase-anon-key"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "supabase_anon_key" {
  secret      = google_secret_manager_secret.supabase_anon_key.id
  secret_data = var.supabase_anon_key
}

resource "google_secret_manager_secret" "supabase_service_role_key" {
  secret_id = "supabase-service-role-key"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "supabase_service_role_key" {
  secret      = google_secret_manager_secret.supabase_service_role_key.id
  secret_data = var.supabase_service_role_key
}

resource "google_secret_manager_secret" "mem0_api_key" {
  secret_id = "mem0-api-key"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "mem0_api_key" {
  secret      = google_secret_manager_secret.mem0_api_key.id
  secret_data = var.mem0_api_key
}

resource "google_secret_manager_secret" "logfire_token" {
  secret_id = "logfire-token"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "logfire_token" {
  secret      = google_secret_manager_secret.logfire_token.id
  secret_data = var.logfire_token
}

resource "google_secret_manager_secret" "knock_api_key" {
  secret_id = "knock-api-key"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "knock_api_key" {
  secret      = google_secret_manager_secret.knock_api_key.id
  secret_data = var.knock_api_key
}

resource "google_secret_manager_secret" "langfuse_secret_key" {
  secret_id = "langfuse-secret-key"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "langfuse_secret_key" {
  secret      = google_secret_manager_secret.langfuse_secret_key.id
  secret_data = var.langfuse_secret_key
}

resource "google_secret_manager_secret" "langfuse_public_key" {
  secret_id = "langfuse-public-key"

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "langfuse_public_key" {
  secret      = google_secret_manager_secret.langfuse_public_key.id
  secret_data = var.langfuse_public_key
}

# -----------------------------------------------------------------------------
# Service Account - Cloud Run identity
# -----------------------------------------------------------------------------

resource "google_service_account" "cloud_run" {
  account_id   = "${var.service_name}-sa"
  display_name = "Glyx MCP Cloud Run Service Account"
}

# Grant access to secrets
resource "google_secret_manager_secret_iam_member" "cloud_run_secrets" {
  for_each = local.secret_env_vars

  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"

  depends_on = [
    google_secret_manager_secret.anthropic_api_key,
    google_secret_manager_secret.openai_api_key,
    google_secret_manager_secret.openrouter_api_key,
    google_secret_manager_secret.supabase_url,
    google_secret_manager_secret.supabase_anon_key,
    google_secret_manager_secret.supabase_service_role_key,
    google_secret_manager_secret.mem0_api_key,
    google_secret_manager_secret.logfire_token,
    google_secret_manager_secret.knock_api_key,
    google_secret_manager_secret.langfuse_secret_key,
    google_secret_manager_secret.langfuse_public_key,
  ]
}

# Grant access to Artifact Registry
resource "google_artifact_registry_repository_iam_member" "cloud_run" {
  location   = google_artifact_registry_repository.glyx.location
  repository = google_artifact_registry_repository.glyx.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.cloud_run.email}"
}

# -----------------------------------------------------------------------------
# Cloud Run Service
# -----------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "glyx_mcp" {
  name     = var.service_name
  location = var.region

  template {
    service_account = google_service_account.cloud_run.email

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    timeout = "${var.timeout}s"

    containers {
      image = "${local.image_name}:latest"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle = true # Scale to zero when idle
      }

      # Plain environment variables
      dynamic "env" {
        for_each = local.env_vars
        content {
          name  = env.key
          value = env.value
        }
      }

      # Secret environment variables from Secret Manager
      dynamic "env" {
        for_each = local.secret_env_vars
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      # TCP startup probe (Cloud Run doesn't support TCP liveness probes)
      startup_probe {
        tcp_socket {
          port = 8080
        }
        initial_delay_seconds = 5
        timeout_seconds       = 10
        period_seconds        = 10
        failure_threshold     = 3
      }
    }

    max_instance_request_concurrency = var.concurrency
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  labels = local.common_labels

  depends_on = [
    google_artifact_registry_repository.glyx,
    google_secret_manager_secret_iam_member.cloud_run_secrets,
  ]
}

# Allow unauthenticated access (public API)
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.glyx_mcp.name
  location = google_cloud_run_v2_service.glyx_mcp.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
