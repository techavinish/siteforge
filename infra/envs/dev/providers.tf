terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  # billing-account-scoped APIs (e.g. budgets) have no home project,
  # so API-call quota is explicitly billed to ours
  user_project_override = true
  billing_project       = var.project_id
}
