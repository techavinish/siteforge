# Proof-of-life: Google's public hello image on Cloud Run through our module.
# In Phase 3 this exact module call pattern deploys the real gateway service.
module "hello" {
  source = "../../modules/cloud-run-service"

  name       = "hello"
  project_id = var.project_id
  region     = var.region
  image      = "us-docker.pkg.dev/cloudrun/container/hello"

  allow_unauthenticated = true
  service_account_email = google_service_account.app_runtime.email

  depends_on = [google_project_service.enabled]
}
