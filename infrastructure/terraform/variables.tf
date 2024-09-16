variable "project_id" {
  description = "The ID of the Google Cloud project"
  type        = string
}

variable "region" {
  description = "The region to deploy resources"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "The zone within the region to deploy resources"
  type        = string
  default     = "us-central1-a"
}

variable "environment" {
  description = "The deployment environment (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "db_instance_name" {
  description = "The name of the database instance"
  type        = string
}

variable "db_name" {
  description = "The name of the database"
  type        = string
}

variable "db_user" {
  description = "The username for the database"
  type        = string
}

variable "db_password" {
  description = "The password for the database user"
  type        = string
  sensitive   = true
}

variable "storage_bucket_names" {
  description = "A list of storage bucket names to create"
  type        = list(string)
}

variable "api_service_name" {
  description = "The name of the API service"
  type        = string
}

variable "api_container_image" {
  description = "The container image for the API service"
  type        = string
}

variable "frontend_service_name" {
  description = "The name of the frontend service"
  type        = string
}

variable "frontend_container_image" {
  description = "The container image for the frontend service"
  type        = string
}

variable "api_min_instances" {
  description = "Minimum number of instances for the API service"
  type        = number
  default     = 1
}

variable "api_max_instances" {
  description = "Maximum number of instances for the API service"
  type        = number
  default     = 5
}

variable "frontend_min_instances" {
  description = "Minimum number of instances for the frontend service"
  type        = number
  default     = 1
}

variable "frontend_max_instances" {
  description = "Maximum number of instances for the frontend service"
  type        = number
  default     = 5
}