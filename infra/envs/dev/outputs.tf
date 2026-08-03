output "hello_url" {
  description = "If this prints a URL that serves traffic, Phase 1 is done"
  value       = module.hello.uri
}

output "app_runtime_sa" {
  value = google_service_account.app_runtime.email
}

output "hosting_url" {
  value = "https://${google_firebase_hosting_site.copilot.site_id}.web.app"
}

output "gateway_url" {
  value = module.gateway.uri
}

# Public client config for the web app (api_key here is an identifier,
# not a secret — Firebase security comes from Auth rules + IAM)
output "firebase_web_config" {
  value = {
    apiKey            = data.google_firebase_web_app_config.copilot.api_key
    authDomain        = data.google_firebase_web_app_config.copilot.auth_domain
    projectId         = var.project_id
    appId             = google_firebase_web_app.copilot.app_id
    messagingSenderId = data.google_firebase_web_app_config.copilot.messaging_sender_id
  }
}
