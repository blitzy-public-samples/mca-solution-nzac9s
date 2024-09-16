#!/bin/bash

# Check for required system dependencies
echo "Checking system dependencies..."
command -v python3 >/dev/null 2>&1 || { echo >&2 "Python 3 is required but not installed. Aborting."; exit 1; }
command -v pip3 >/dev/null 2>&1 || { echo >&2 "pip3 is required but not installed. Aborting."; exit 1; }
command -v node >/dev/null 2>&1 || { echo >&2 "Node.js is required but not installed. Aborting."; exit 1; }
command -v npm >/dev/null 2>&1 || { echo >&2 "npm is required but not installed. Aborting."; exit 1; }
command -v git >/dev/null 2>&1 || { echo >&2 "Git is required but not installed. Aborting."; exit 1; }

# Install necessary Python packages
echo "Installing Python packages..."
pip3 install -r requirements.txt

# Set up Node.js and npm dependencies
echo "Setting up Node.js dependencies..."
npm install

# Configure Google Cloud SDK
echo "Configuring Google Cloud SDK..."
# HUMAN ASSISTANCE NEEDED
# The following block needs to be customized based on the specific Google Cloud project details
gcloud init
gcloud auth application-default login

# Set up local database for development
echo "Setting up local database..."
# HUMAN ASSISTANCE NEEDED
# The following block needs to be customized based on the specific database being used (e.g., PostgreSQL, MySQL)
# Example for PostgreSQL:
# createdb mydatabase
# psql mydatabase < schema.sql

# Initialize Git hooks for pre-commit checks
echo "Setting up Git hooks..."
cp scripts/pre-commit .git/hooks/
chmod +x .git/hooks/pre-commit

echo "Environment setup complete!"