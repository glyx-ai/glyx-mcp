# =============================================================================
# Local Values
# =============================================================================

locals {
  # Common labels for all resources
  common_labels = {
    environment = var.environment
    managed_by  = "terraform"
    project     = "glyx"
    service     = var.service_name
  }

  # Artifact Registry image path
  image_name = "${var.region}-docker.pkg.dev/${var.project_id}/glyx/${var.service_name}"

  # Environment variables for Cloud Run
  # Note: PORT is reserved and auto-set by Cloud Run
  env_vars = {
    ENVIRONMENT = var.environment
  }

  # Secret environment variables (references to Secret Manager)
  secret_env_vars = {
    ANTHROPIC_API_KEY         = google_secret_manager_secret.anthropic_api_key.secret_id
    OPENAI_API_KEY            = google_secret_manager_secret.openai_api_key.secret_id
    OPENROUTER_API_KEY        = google_secret_manager_secret.openrouter_api_key.secret_id
    SUPABASE_URL              = google_secret_manager_secret.supabase_url.secret_id
    SUPABASE_ANON_KEY         = google_secret_manager_secret.supabase_anon_key.secret_id
    SUPABASE_SERVICE_ROLE_KEY = google_secret_manager_secret.supabase_service_role_key.secret_id
    MEM0_API_KEY              = google_secret_manager_secret.mem0_api_key.secret_id
    LOGFIRE_TOKEN             = google_secret_manager_secret.logfire_token.secret_id
    KNOCK_API_KEY             = google_secret_manager_secret.knock_api_key.secret_id
  }
}
