# Cost guardrail as code (design-review gap #2).
# Alerts at 50/80/100% of ₹2000/month. Created only when billing_account_id is set.

# the budgets API stores project NUMBERS, not ids — resolve it to avoid a perma-diff
data "google_project" "this" {
  project_id = var.project_id
}

resource "google_billing_budget" "dev" {
  count = var.billing_account_id == "" ? 0 : 1

  billing_account = var.billing_account_id
  display_name    = "siteforge-dev monthly"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "INR"
      units         = "2000"
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.8
  }
  threshold_rules {
    threshold_percent = 1.0
  }

  depends_on = [google_project_service.enabled]
}
