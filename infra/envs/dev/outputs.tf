output "hello_url" {
  description = "If this prints a URL that serves traffic, Phase 1 is done"
  value       = module.hello.uri
}

output "app_runtime_sa" {
  value = google_service_account.app_runtime.email
}
