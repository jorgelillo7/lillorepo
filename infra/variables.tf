variable "billing_account" {
  description = "Billing account id (XXXXXX-XXXXXX-XXXXXX) that owns both projects and the budgets."
  type        = string

  # An empty value (a missing CI secret) would otherwise plan to replace every
  # budget instead of failing.
  validation {
    condition     = can(regex("^[0-9A-F]{6}-[0-9A-F]{6}-[0-9A-F]{6}$", var.billing_account))
    error_message = "billing_account must look like XXXXXX-XXXXXX-XXXXXX (set TF_BILLING_ACCOUNT in CI)."
  }
}
