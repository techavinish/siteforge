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

# The agent — the product's brain, reaching Cloud SQL over the unix socket
# with its password injected straight from Secret Manager.
module "agent" {
  source = "../../modules/cloud-run-service"

  name       = "agent"
  project_id = var.project_id
  region     = var.region
  image      = "asia-south1-docker.pkg.dev/${var.project_id}/services/agent:bootstrap"
  memory     = "1Gi" # langgraph + model clients need headroom

  allow_unauthenticated = true # firebase ID tokens verified in-app
  service_account_email = google_service_account.app_runtime.email

  cloudsql_instances = [google_sql_database_instance.main.connection_name]

  env = {
    CLOUDSQL_CONN = google_sql_database_instance.main.connection_name
    DB_USER       = google_sql_user.app.name
    DB_NAME       = google_sql_database.siteforge.name
    GCP_PROJECT   = var.project_id
    RAG_URL       = module.rag.uri # hosted generations get grounded too
  }

  secret_env = {
    DB_PASS            = "db-password"
    OPENROUTER_API_KEY = "openrouter-api-key"
    PEXELS_API_KEY     = "pexels-api-key"
    SENTRY_DSN         = "sentry-dsn"
  }

  depends_on = [google_project_service.enabled]
}

# retrieval — same knowledge base as local, reading the corpus in Cloud SQL
module "rag" {
  source = "../../modules/cloud-run-service"

  name       = "rag"
  project_id = var.project_id
  region     = var.region
  image      = "asia-south1-docker.pkg.dev/${var.project_id}/services/rag:bootstrap"
  memory     = "1Gi" # onnx embedding model resident in memory

  allow_unauthenticated = true # non-sensitive guidance content; called by agent + mcp
  service_account_email = google_service_account.app_runtime.email

  cloudsql_instances = [google_sql_database_instance.main.connection_name]

  env = {
    CLOUDSQL_CONN = google_sql_database_instance.main.connection_name
    DB_USER       = google_sql_user.app.name
    DB_NAME       = google_sql_database.siteforge.name
  }

  secret_env = {
    DB_PASS    = "db-password"
    SENTRY_DSN = "sentry-dsn"
  }

  depends_on = [google_project_service.enabled]
}

# the remote MCP surface — any MCP client on the internet can build and
# publish SiteForge sites through this
module "mcp" {
  source = "../../modules/cloud-run-service"

  name       = "mcp"
  project_id = var.project_id
  region     = var.region
  image      = "asia-south1-docker.pkg.dev/${var.project_id}/services/mcp:bootstrap"
  memory     = "1Gi"

  allow_unauthenticated = true
  service_account_email = google_service_account.app_runtime.email

  env = {
    GCP_PROJECT = var.project_id
    RAG_URL     = module.rag.uri
  }

  secret_env = {
    OPENROUTER_API_KEY = "openrouter-api-key"
    PEXELS_API_KEY     = "pexels-api-key"
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_iam_member" "runtime_reads_sentry" {
  secret_id = "sentry-dsn"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app_runtime.email}"
}

# publish.py creates + releases hosting sites as the runtime SA
resource "google_project_iam_member" "runtime_hosting_admin" {
  project = var.project_id
  role    = "roles/firebasehosting.admin"
  member  = "serviceAccount:${google_service_account.app_runtime.email}"
}

# these secrets were created via gcloud — terraform only manages access
resource "google_secret_manager_secret_iam_member" "runtime_reads_openrouter" {
  secret_id = "openrouter-api-key"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app_runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "runtime_reads_pexels" {
  secret_id = "pexels-api-key"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app_runtime.email}"
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
