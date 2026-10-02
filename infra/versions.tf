terraform {
  required_version = ">= 1.16"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.5"
    }
  }

  # Local until the state bucket exists; see README.md → "State".
  backend "local" {}
}

provider "google" {
  region = "europe-southwest1"
}

# Budgets are billing-account resources: with user credentials the Budget API
# needs a quota project to bill the call to. Scoped to budgets only, so every
# other call keeps working without enabling more APIs in the quota project.
provider "google" {
  alias                 = "billing"
  user_project_override = true
  billing_project       = "biwenger-tools"
}
