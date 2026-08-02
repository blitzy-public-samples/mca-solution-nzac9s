#!/bin/bash

# Every path used below is derived from this script's own location instead of from
# the caller's working directory. The backend dependency manifest lives at
# backend/requirements.txt, so a bare cwd-relative reference to it finds nothing
# from the repository root, while the repository's own paths find nothing from
# backend/ - no single directory makes a cwd-relative script correct.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_REQUIREMENTS="${REPO_ROOT}/backend/requirements.txt"
FRONTEND_DIR="${REPO_ROOT}/frontend"

# Check for required system dependencies
echo "Checking system dependencies..."
command -v node >/dev/null 2>&1 || { echo >&2 "Node.js is required but not installed. Aborting."; exit 1; }
command -v npm >/dev/null 2>&1 || { echo >&2 "npm is required but not installed. Aborting."; exit 1; }
command -v git >/dev/null 2>&1 || { echo >&2 "Git is required but not installed. Aborting."; exit 1; }

# Locate a Python 3.9 interpreter specifically. The backend manifest is pinned for
# 3.9 - the runtime declared at .github/workflows/ci.yml line 19 and
# infrastructure/docker/Dockerfile.backend line 2 - so a generic python3 must not
# be trusted: on a current host it is a far newer interpreter, and several of the
# pinned distributions publish no wheel for it.
PYTHON39=""
for candidate in python3.9 python3 python; do
    command -v "${candidate}" >/dev/null 2>&1 || continue
    if "${candidate}" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 9) else 1)' >/dev/null 2>&1; then
        PYTHON39="${candidate}"
        break
    fi
done
[ -n "${PYTHON39}" ] || { echo >&2 "Python 3.9 is required by ${BACKEND_REQUIREMENTS} but no 3.9 interpreter was found on PATH (tried python3.9, python3, python). Aborting."; exit 1; }
"${PYTHON39}" -m pip --version >/dev/null 2>&1 || { echo >&2 "pip is required for ${PYTHON39} but is not available. Aborting."; exit 1; }
echo "Using $("${PYTHON39}" --version 2>&1) from $(command -v "${PYTHON39}")"

# Install necessary Python packages. A failure here has to stop the bootstrap:
# carrying on would hand back an environment that only looks provisioned.
echo "Installing Python packages..."
[ -f "${BACKEND_REQUIREMENTS}" ] || { echo >&2 "Backend dependency manifest not found at ${BACKEND_REQUIREMENTS}. Aborting."; exit 1; }
"${PYTHON39}" -m pip install -r "${BACKEND_REQUIREMENTS}" || { echo >&2 "Backend dependency installation failed. Aborting."; exit 1; }

# Confirm the installed Google Cloud closure is still warning-free on this
# interpreter. The manifest pins that closure exactly for this reason; should a
# drifted resolution ever reintroduce the "Python 3.9 is past its end of life"
# FutureWarning, promoting warnings to errors turns these imports into failures so
# the bootstrap stops here instead of handing over a silently degraded foundation.
echo "Verifying Google Cloud client imports..."
"${PYTHON39}" -W error::FutureWarning -c 'from google.cloud import storage, vision; from google.cloud import logging as cloud_logging; assert storage.Client and vision.Image and cloud_logging.Client' || { echo >&2 "Installed Google Cloud clients emit runtime-support warnings or failed to import under ${PYTHON39}. Aborting."; exit 1; }

# Set up Node.js and npm dependencies
echo "Setting up Node.js dependencies..."
[ -f "${FRONTEND_DIR}/package.json" ] || { echo >&2 "Frontend package manifest not found at ${FRONTEND_DIR}/package.json. Aborting."; exit 1; }
npm install --prefix "${FRONTEND_DIR}" || { echo >&2 "Frontend dependency installation failed. Aborting."; exit 1; }

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
cp "${REPO_ROOT}/scripts/pre-commit" "${REPO_ROOT}/.git/hooks/"
chmod +x "${REPO_ROOT}/.git/hooks/pre-commit"

echo "Environment setup complete!"