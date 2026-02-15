# =============================================================================
# Outputs
# =============================================================================

output "service_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.glyx_mcp.uri
}

output "service_name" {
  description = "Cloud Run service name"
  value       = google_cloud_run_v2_service.glyx_mcp.name
}

output "artifact_registry_url" {
  description = "Artifact Registry repository URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.glyx.repository_id}"
}

output "image_url" {
  description = "Full container image URL"
  value       = local.image_name
}

output "service_account_email" {
  description = "Cloud Run service account email"
  value       = google_service_account.cloud_run.email
}

output "mcp_endpoint" {
  description = "MCP protocol endpoint"
  value       = "${google_cloud_run_v2_service.glyx_mcp.uri}/mcp"
}

output "api_docs_url" {
  description = "API documentation URL"
  value       = "${google_cloud_run_v2_service.glyx_mcp.uri}/docs"
}

# GitHub Actions CI/CD outputs (only when WIF is enabled)
output "github_actions_workload_identity_provider" {
  description = "Workload Identity Provider for GitHub Actions (set as GCP_WORKLOAD_IDENTITY_PROVIDER secret)"
  value       = var.enable_github_actions_wif ? google_iam_workload_identity_pool_provider.github[0].name : null
}

output "github_actions_service_account" {
  description = "Service account for GitHub Actions (set as GCP_SERVICE_ACCOUNT secret)"
  value       = var.enable_github_actions_wif ? google_service_account.github_actions[0].email : null
}
