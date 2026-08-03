resource "google_cloud_run_v2_service" "this" {
  name     = var.name
  location = var.region
  project  = var.project_id

  # dev convenience; flip to true in the prod env
  deletion_protection = false

  lifecycle {
    # the API populates a service-level scaling block we don't manage
    # (we scale via template.scaling) — ignore it to avoid a perma-diff.
    # image is ignored because CI deploys new tags outside terraform:
    # terraform owns the service's SHAPE, CI owns its CONTENTS.
    ignore_changes = [scaling, template[0].containers[0].image]
  }

  template {
    service_account = var.service_account_email

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.image

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle = var.cpu_idle
      }

      dynamic "env" {
        for_each = var.env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      dynamic "volume_mounts" {
        for_each = length(var.cloudsql_instances) > 0 ? [1] : []
        content {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }

    dynamic "volumes" {
      for_each = length(var.cloudsql_instances) > 0 ? [1] : []
      content {
        name = "cloudsql"
        cloud_sql_instance {
          instances = var.cloudsql_instances
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  count = var.allow_unauthenticated ? 1 : 0

  name     = google_cloud_run_v2_service.this.name
  location = var.region
  project  = var.project_id
  role     = "roles/run.invoker"
  member   = "allUsers"
}
