# State backend — WHERE terraform remembers what it has created.
#
# The first apply ran with local state (chicken-and-egg: this bucket can't
# store the state of its own creation — it was bootstrapped with gcloud).
# State was then migrated here with: terraform init -migrate-state
terraform {
  backend "gcs" {
    bucket = "siteforge-dev-3977-tfstate"
    prefix = "envs/dev"
  }
}
