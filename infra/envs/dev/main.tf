# The real front door. Public because Firebase Hosting rewrites /api/** here;
# actual auth happens inside via Firebase ID token verification.
# CI replaces the image tag on every merge (terraform ignores image changes).
module "gateway" {
  source = "../../modules/cloud-run-service"

  name       = "gateway"
  project_id = var.project_id
  region     = var.region
  image      = "asia-south1-docker.pkg.dev/${var.project_id}/services/gateway:bootstrap"

  allow_unauthenticated = true
  service_account_email = google_service_account.app_runtime.email

  env = {
    DB_CONNECTION_NAME = google_sql_database_instance.main.connection_name
    DB_NAME            = google_sql_database.siteforge.name
    DB_USER            = google_sql_user.app.name
  }

  depends_on = [google_project_service.enabled]
}

# Proof-of-life: Google's public hello image on Cloud Run through our module.
# Kept as the cheapest possible smoke test of the module itself.
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
