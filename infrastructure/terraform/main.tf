# Main Terraform configuration for MCA application processing system

# Provider configuration
provider "google" {
  project = var.project_id
  region  = var.region
}

# VPC network and subnets
resource "google_compute_network" "mca_network" {
  name                    = "mca-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "mca_subnet" {
  name          = "mca-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.mca_network.id
}

# Google Cloud SQL instance for PostgreSQL
resource "google_sql_database_instance" "mca_db" {
  name             = "mca-db-instance"
  database_version = "POSTGRES_13"
  region           = var.region

  settings {
    tier = "db-f1-micro"
    ip_configuration {
      ipv4_enabled    = true
      private_network = google_compute_network.mca_network.id
    }
  }
}

resource "google_sql_database" "mca_database" {
  name     = "mca_database"
  instance = google_sql_database_instance.mca_db.name
}

# Google Cloud Storage buckets
resource "google_storage_bucket" "mca_documents" {
  name     = "${var.project_id}-mca-documents"
  location = var.region
}

resource "google_storage_bucket" "mca_processed" {
  name     = "${var.project_id}-mca-processed"
  location = var.region
}

# Google Cloud Functions for webhook handling
resource "google_cloudfunctions_function" "webhook_handler" {
  name        = "mca-webhook-handler"
  description = "Function to handle incoming webhooks"
  runtime     = "nodejs14"

  available_memory_mb   = 256
  source_archive_bucket = google_storage_bucket.mca_documents.name
  source_archive_object = "webhook-handler.zip"
  trigger_http          = true
  entry_point           = "handleWebhook"
}

# Google Cloud Pub/Sub topics and subscriptions
resource "google_pubsub_topic" "mca_notifications" {
  name = "mca-notifications"
}

resource "google_pubsub_subscription" "mca_notifications_sub" {
  name  = "mca-notifications-sub"
  topic = google_pubsub_topic.mca_notifications.name

  ack_deadline_seconds = 20
}

# Google Cloud Run services for API and frontend
resource "google_cloud_run_service" "mca_api" {
  name     = "mca-api"
  location = var.region

  template {
    spec {
      containers {
        image = "gcr.io/${var.project_id}/mca-api:latest"
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}

resource "google_cloud_run_service" "mca_frontend" {
  name     = "mca-frontend"
  location = var.region

  template {
    spec {
      containers {
        image = "gcr.io/${var.project_id}/mca-frontend:latest"
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}

# Google Cloud IAM roles and service accounts
resource "google_service_account" "mca_service_account" {
  account_id   = "mca-service-account"
  display_name = "MCA Service Account"
}

resource "google_project_iam_member" "mca_service_account_roles" {
  project = var.project_id
  role    = "roles/editor"
  member  = "serviceAccount:${google_service_account.mca_service_account.email}"
}

# HUMAN ASSISTANCE NEEDED
# The following IAM roles might need to be more granular for production use.
# Please review and adjust according to the principle of least privilege.
resource "google_project_iam_member" "mca_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.mca_service_account.email}"
}

resource "google_project_iam_member" "mca_cloudsql_admin" {
  project = var.project_id
  role    = "roles/cloudsql.admin"
  member  = "serviceAccount:${google_service_account.mca_service_account.email}"
}

resource "google_project_iam_member" "mca_pubsub_admin" {
  project = var.project_id
  role    = "roles/pubsub.admin"
  member  = "serviceAccount:${google_service_account.mca_service_account.email}"
}