#!/bin/bash

set -e

# Authenticate with Google Cloud
echo "Authenticating with Google Cloud..."
gcloud auth activate-service-account --key-file=${GCP_SERVICE_ACCOUNT_KEY}
gcloud config set project ${GCP_PROJECT_ID}

# Build and push Docker images
echo "Building and pushing Docker images..."
docker build -t gcr.io/${GCP_PROJECT_ID}/backend:latest ./backend
docker push gcr.io/${GCP_PROJECT_ID}/backend:latest

# Apply Terraform configurations
echo "Applying Terraform configurations..."
cd terraform
terraform init
terraform apply -auto-approve
cd ..

# Deploy backend to Google Cloud Run
echo "Deploying backend to Google Cloud Run..."
gcloud run deploy backend \
    --image gcr.io/${GCP_PROJECT_ID}/backend:latest \
    --platform managed \
    --region ${GCP_REGION} \
    --allow-unauthenticated

# Deploy frontend to Google Cloud Storage and set up Cloud CDN
echo "Deploying frontend to Google Cloud Storage..."
gsutil rsync -R ./frontend/build gs://${GCP_FRONTEND_BUCKET}

echo "Setting up Cloud CDN..."
gcloud compute backend-buckets create ${GCP_FRONTEND_BUCKET}-backend \
    --gcs-bucket-name=${GCP_FRONTEND_BUCKET}
gcloud compute url-maps create ${GCP_FRONTEND_BUCKET}-url-map \
    --default-backend-bucket=${GCP_FRONTEND_BUCKET}-backend
gcloud compute target-http-proxies create ${GCP_FRONTEND_BUCKET}-http-proxy \
    --url-map=${GCP_FRONTEND_BUCKET}-url-map
gcloud compute forwarding-rules create ${GCP_FRONTEND_BUCKET}-http-rule \
    --global \
    --target-http-proxy=${GCP_FRONTEND_BUCKET}-http-proxy \
    --ports=80

# Update database schema if necessary
echo "Updating database schema..."
# HUMAN ASSISTANCE NEEDED
# Add commands to update the database schema. This might involve running migrations or executing SQL scripts.
# Example: 
# gcloud sql connect ${GCP_DB_INSTANCE} --user=root < ./db/migrations/latest.sql

# Run post-deployment tests
echo "Running post-deployment tests..."
# HUMAN ASSISTANCE NEEDED
# Add commands to run post-deployment tests. This might involve calling a separate test script or running specific test commands.
# Example:
# ./scripts/run_post_deploy_tests.sh

# Notify team of deployment status
echo "Notifying team of deployment status..."
# HUMAN ASSISTANCE NEEDED
# Add commands to notify the team about the deployment status. This might involve sending an email, posting to a Slack channel, or updating a status page.
# Example:
# curl -X POST -H 'Content-type: application/json' --data '{"text":"Deployment completed successfully!"}' ${SLACK_WEBHOOK_URL}

echo "Deployment completed successfully!"