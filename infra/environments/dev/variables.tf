variable "aws_region" {
  description = "AWS region for the development environment."
  type        = string
}

variable "project_name" {
  description = "Short project identifier used in resource names and tags."
  type        = string
  default     = "hydrosim-cloud"
}

variable "tags" {
  description = "Additional tags applied to development resources."
  type        = map(string)
  default     = {}
}
