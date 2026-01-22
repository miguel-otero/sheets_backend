#!/bin/bash

# ----------------------------------------------------------------------------
# This script assists in setting up GCP (Google Cloud Platform) configurations
# for a user. Specifically, it checks if the GCP account and project
# environment variables are set, and if not, prompts the user for them.
#
# Once the user provides these values, the script saves them to a .env file
# for persistent storage. The values are then applied using the `gcloud`
# command-line tool to ensure the correct GCP account and project settings
# are active.
#
# It's designed to simplify GCP configuration management and ensure that
# users always have the necessary settings available, making it especially
# beneficial in development or CI/CD environments.
# ---------------------------------------------------------------------------

# Path to the .env file
env_file="./conn/.env"

# Source the .env file to load any existing variables
. $env_file

# Check if the ACCOUNT variable is empty
if [ -z "$ACCOUNT" ]; then
  # Prompt the user to enter their GCP account
  read -p "GCP account: " ACCOUNT
  # Append the ACCOUNT variable and its value to the .env file
  echo "ACCOUNT=$ACCOUNT" >> $env_file
fi

# Check if the PROJECT variable is empty
if [ -z "$PROJECT" ]; then
  # Prompt the user to enter their GCP project
  read -p "GCP project: " PROJECT
  # Append the PROJECT variable and its value to the .env file
  echo "PROJECT=$PROJECT" >> $env_file
fi

# Check if the REGION variable is empty
if [ -z "$REGION" ]; then
  # Prompt the user to enter their GCP project
  read -p "GCP region: " REGION
  # Append the PROJECT variable and its value to the .env file
  echo "REGION=$REGION" >> $env_file
fi

# Set GCP account and project variables using gcloud CLI
gcloud config set account $ACCOUNT
gcloud config set project $PROJECT
gcloud config set compute/region $REGION
