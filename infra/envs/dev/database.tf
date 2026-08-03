# Operational database. Smallest tier for dev — the instance is the one
# fixed cost in the project (~$9/mo, covered by trial credits).
resource "google_sql_database_instance" "main" {
  name             = "siteforge-dev"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier    = "db-f1-micro"
    edition = "ENTERPRISE"

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }

    ip_configuration {
      # public IP + connector auth for dev simplicity; Cloud Run reaches it
      # via the built-in unix socket, local via cloud-sql-proxy — nobody
      # connects with a bare IP + password over the internet
      ipv4_enabled = true
    }
  }

  deletion_protection = false # dev only

  depends_on = [google_project_service.enabled]
}

resource "google_sql_database" "siteforge" {
  name     = "siteforge"
  instance = google_sql_database_instance.main.name
}

# password exists only inside terraform state + secret manager —
# never in a file, never in git
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_sql_user" "app" {
  name     = "app"
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "db-password"

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db.result
}

# the runtime SA may read THIS secret — not all secrets
resource "google_secret_manager_secret_iam_member" "runtime_reads_db" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app_runtime.email}"
}

# Cloud Run's unix-socket path to Cloud SQL requires the client role
resource "google_project_iam_member" "runtime_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.app_runtime.email}"
}

output "db_connection_name" {
  description = "Instance connection name for cloud-sql-proxy and Cloud Run"
  value       = google_sql_database_instance.main.connection_name
}
