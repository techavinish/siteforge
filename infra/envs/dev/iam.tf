# Runtime identity for our Cloud Run services.
# Services never run as the (over-privileged) default compute SA —
# this SA starts with zero roles and earns them one need at a time.
resource "google_service_account" "app_runtime" {
  account_id   = "app-runtime"
  display_name = "SiteForge app runtime"
  project      = var.project_id

  depends_on = [google_project_service.enabled]
}
