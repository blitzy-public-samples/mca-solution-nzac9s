# Output values for the Terraform configuration

# VPC network details
output "vpc_id" {
  description = "The ID of the VPC"
  value       = google_compute_network.main_vpc.id
}

output "subnet_ids" {
  description = "The IDs of the subnets"
  value       = google_compute_subnetwork.subnets[*].id
}

# Database connection information
output "database_instance_name" {
  description = "The name of the Cloud SQL instance"
  value       = google_sql_database_instance.main.name
}

output "database_connection_name" {
  description = "The connection name of the Cloud SQL instance"
  value       = google_sql_database_instance.main.connection_name
}

# Storage bucket URLs
output "storage_bucket_url" {
  description = "The URL of the main storage bucket"
  value       = google_storage_bucket.main_bucket.url
}

# API and frontend service URLs
output "api_service_url" {
  description = "The URL of the API service"
  value       = google_cloud_run_service.api.status[0].url
}

output "frontend_service_url" {
  description = "The URL of the frontend service"
  value       = google_cloud_run_service.frontend.status[0].url
}

# IAM service account keys
output "api_service_account_key" {
  description = "The service account key for the API"
  value       = google_service_account_key.api_key.private_key
  sensitive   = true
}

output "frontend_service_account_key" {
  description = "The service account key for the frontend"
  value       = google_service_account_key.frontend_key.private_key
  sensitive   = true
}

# HUMAN ASSISTANCE NEEDED
# Please review the following outputs and ensure they align with the actual resources created in your Terraform configuration:
# - Verify that the resource names (e.g., google_compute_network.main_vpc, google_sql_database_instance.main) match your actual resource names.
# - Confirm that all necessary outputs are included and that no sensitive information is exposed unintentionally.
# - Check if any additional outputs are required for your specific use case.