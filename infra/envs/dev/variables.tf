variable "project_id" {
  description = "GCP project ID (globally unique)"
  type        = string
}

variable "region" {
  description = "Primary region for all resources"
  type        = string
  default     = "asia-south1" # Mumbai
}

variable "billing_account_id" {
  description = "Billing account ID (XXXXXX-XXXXXX-XXXXXX) — enables the budget alert when set"
  type        = string
  default     = ""
}
