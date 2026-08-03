variable "name" {
  description = "Service name"
  type        = string
}

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "image" {
  description = "Full container image URL"
  type        = string
}

variable "env" {
  description = "Plain-text environment variables (secrets are wired separately via Secret Manager)"
  type        = map(string)
  default     = {}
}

variable "service_account_email" {
  description = "Runtime identity of the service; null = compute default SA"
  type        = string
  default     = null
}

variable "min_instances" {
  type    = number
  default = 0 # scale to zero — the free-tier lever
}

variable "max_instances" {
  type    = number
  default = 2 # low ceiling in dev so a bug can't fan out into a bill
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "512Mi"
}

variable "cpu_idle" {
  description = "true = CPU only during requests (web services). false = always-on CPU (Temporal workers)"
  type        = bool
  default     = true
}

variable "allow_unauthenticated" {
  description = "Expose publicly. Only the gateway should ever set this in prod."
  type        = bool
  default     = false
}
