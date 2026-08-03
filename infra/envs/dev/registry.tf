# Home for our service images. One repo, one image path per service:
# asia-south1-docker.pkg.dev/<project>/services/<service>:<tag>
resource "google_artifact_registry_repository" "services" {
  repository_id = "services"
  format        = "DOCKER"
  location      = var.region
  description   = "SiteForge service images"

  # dev hygiene: keep only recent images, don't hoard layers
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }
  cleanup_policies {
    id     = "purge-old"
    action = "DELETE"
    condition {
      older_than = "2592000s" # 30 days
    }
  }

  depends_on = [google_project_service.enabled]
}
