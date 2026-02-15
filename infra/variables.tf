# =============================================================================
# Input Variables
# =============================================================================

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for deployment"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be development, staging, or production."
  }
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
  default     = "glyx-mcp"
}

# =============================================================================
# Secrets (sensitive)
# =============================================================================

variable "anthropic_api_key" {
  description = "Anthropic API key"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openrouter_api_key" {
  description = "OpenRouter API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "supabase_url" {
  description = "Supabase project URL"
  type        = string
}

variable "supabase_anon_key" {
  description = "Supabase anon/public key"
  type        = string
  sensitive   = true
}

variable "supabase_service_role_key" {
  description = "Supabase service role key"
  type        = string
  sensitive   = true
}

variable "mem0_api_key" {
  description = "Mem0 API key for memory management"
  type        = string
  sensitive   = true
  default     = ""
}

variable "logfire_token" {
  description = "Logfire observability token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "knock_api_key" {
  description = "Knock API key for notifications"
  type        = string
  sensitive   = true
}

variable "langfuse_secret_key" {
  description = "Langfuse secret key for observability"
  type        = string
  sensitive   = true
}

variable "langfuse_public_key" {
  description = "Langfuse public key"
  type        = string
  sensitive   = true
}

variable "langfuse_base_url" {
  description = "Langfuse API base URL"
  type        = string
  default     = "https://us.cloud.langfuse.com"
}

# =============================================================================
# Resource Configuration
# =============================================================================

variable "memory" {
  description = "Memory allocation for Cloud Run (e.g., 512Mi, 1Gi, 2Gi)"
  type        = string
  default     = "1Gi"
}

variable "cpu" {
  description = "CPU allocation for Cloud Run"
  type        = string
  default     = "1"
}

variable "min_instances" {
  description = "Minimum number of instances"
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum number of instances"
  type        = number
  default     = 10
}

variable "timeout" {
  description = "Request timeout in seconds"
  type        = number
  default     = 300
}

variable "concurrency" {
  description = "Max concurrent requests per instance"
  type        = number
  default     = 80
}

# =============================================================================
# CI/CD Configuration
# =============================================================================

variable "github_repo" {
  description = "GitHub repository (owner/repo) for Workload Identity Federation"
  type        = string
  default     = "glyx-ai/glyx-mcp"
}

variable "enable_github_actions_wif" {
  description = "Enable Workload Identity Federation for GitHub Actions (requires IAM admin permissions)"
  type        = bool
  default     = false
}

variable "image_tag" {
  description = "Docker image tag (commit SHA for CI, 'latest' for local)"
  type        = string
  default     = "latest"
}
