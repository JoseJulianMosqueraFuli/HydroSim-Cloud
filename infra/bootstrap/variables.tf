variable "aws_region" {
  description = "AWS region where the Terraform state bucket is created."
  type        = string
}

variable "project_name" {
  description = "Short project identifier used in resource names and tags."
  type        = string
  default     = "hydrosim-cloud"
}

variable "tags" {
  description = "Additional tags applied to bootstrap resources."
  type        = map(string)
  default     = {}
}
