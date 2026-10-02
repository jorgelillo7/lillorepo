# €1 monthly alerts at the billing-account level. One is account-wide (no
# project filter); one watches the paid Gemini project outside this repo.
locals {
  budgets = {
    account = {
      id           = "c2508ba2-92e4-4384-b0e3-450538bbb7f3"
      display_name = "€1 Alerta de presupuesto mensual"
      projects     = null
      thresholds   = [0.5, 0.9, 1.0, 1.5]
    }
    be_water = {
      id           = "b8fdf8a2-2043-428a-b53d-54d230459f89"
      display_name = "be-water: €1 alerta mensual"
      projects     = ["projects/${local.be_water_number}"]
      thresholds   = [0.5, 0.9, 1.0]
    }
    gemini_paid = {
      id           = "a53f6fb1-a8fe-4d83-97c9-531536ae6a5e"
      display_name = "be-water gemini-imagen: €1 alerta mensual"
      projects     = ["projects/685490759208"]
      thresholds   = [0.5, 0.9, 1.0]
    }
  }
}

resource "google_billing_budget" "this" {
  for_each = local.budgets
  provider = google.billing

  billing_account = var.billing_account
  display_name    = each.value.display_name

  amount {
    specified_amount {
      currency_code = "EUR"
      units         = "1"
    }
  }

  budget_filter {
    projects               = each.value.projects
    calendar_period        = "MONTH"
    credit_types_treatment = "INCLUDE_ALL_CREDITS"
  }

  dynamic "threshold_rules" {
    for_each = each.value.thresholds
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }
}
