terraform {
  backend "s3" {
    key          = "hydrosim-cloud/dev/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
