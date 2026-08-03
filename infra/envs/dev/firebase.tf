# Attaches Firebase to the existing GCP project — Firebase is a layer
# over GCP, not a separate cloud; same project, same billing, same IAM.
resource "google_firebase_project" "default" {
  provider = google-beta
  project  = var.project_id

  depends_on = [google_project_service.enabled]
}

# The registered client app — its config (below) is what the React app
# uses to talk to Firebase Auth. That config is public by design.
resource "google_firebase_web_app" "copilot" {
  provider     = google-beta
  project      = var.project_id
  display_name = "SiteForge Copilot"

  depends_on = [google_firebase_project.default]
}

data "google_firebase_web_app_config" "copilot" {
  provider   = google-beta
  project    = var.project_id
  web_app_id = google_firebase_web_app.copilot.app_id
}

# Deployment Surface 1 — where the copilot UI (and later, generated
# customer sites) are served from.
resource "google_firebase_hosting_site" "copilot" {
  provider = google-beta
  project  = var.project_id
  site_id  = var.project_id # -> https://siteforge-dev-3977.web.app

  depends_on = [google_firebase_project.default]
}

# Initializes Firebase Auth (Identity Platform) for the project.
# NOTE: the Google sign-in *provider* is enabled once in the console —
# its OAuth consent screen cannot be created by API (documented gap).
resource "google_identity_platform_config" "auth" {
  provider = google-beta
  project  = var.project_id

  authorized_domains = [
    "localhost",
    "${var.project_id}.web.app",
    "${var.project_id}.firebaseapp.com",
  ]

  depends_on = [google_firebase_project.default]
}
