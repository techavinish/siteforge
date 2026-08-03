# Keyless CI auth — Workload Identity Federation.
#
# GitHub Actions gets NO stored key. On each run, GitHub issues the job a
# short-lived OIDC token; Google verifies it and, only if it comes from
# THIS repo, lets the job act as the deployer service account. Nothing to
# leak, nothing to rotate.

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.enabled]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }

  # the trust boundary: ONLY workflows in this repo can authenticate
  attribute_condition = "assertion.repository == \"techavinish/siteforge\""
}

resource "google_service_account" "deployer" {
  account_id   = "github-deployer"
  display_name = "GitHub Actions deployer"

  depends_on = [google_project_service.enabled]
}

# let workflows from our repo impersonate the deployer
resource "google_service_account_iam_member" "wif_binding" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/techavinish/siteforge"
}

# what the deployer may do — push images, deploy services, read for plans
resource "google_project_iam_member" "deployer_roles" {
  for_each = toset([
    "roles/artifactregistry.writer",
    "roles/run.admin",
    "roles/viewer",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# deploying a Cloud Run service that runs AS app-runtime requires
# permission to "act as" that identity
resource "google_service_account_iam_member" "deployer_actas_runtime" {
  service_account_id = google_service_account.app_runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

# terraform plan in CI reads state from the bucket
resource "google_storage_bucket_iam_member" "deployer_state" {
  bucket = "siteforge-dev-3977-tfstate"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.deployer.email}"
}

output "wif_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_sa" {
  value = google_service_account.deployer.email
}
