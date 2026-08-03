output "uri" {
  description = "Public HTTPS URL of the service"
  value       = google_cloud_run_v2_service.this.uri
}

output "name" {
  value = google_cloud_run_v2_service.this.name
}
