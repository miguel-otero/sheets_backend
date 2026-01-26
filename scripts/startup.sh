#!/bin/bash

export DEBIAN_FRONTEND=noninteractive

# Function to display help menu
Usage() {
    echo "Usage: $0 [OPTIONS] [-t TOOL]"
    echo
    echo "Options:"
    echo "  -h|-help    Show this help message and exit"
    echo
    echo "Parameters:"
    echo "  TOOL       Tool for be installed (aws, gcloud, az, docker, jq, unzip)"
    echo
    echo " Example:"
    echo "     $0 -t gcloud"
    echo "     $0 -t aws -t jq"
}


# Function to install Docker
DockerInstall() {
  # Update the package list and install packages to allow apt to use a repository over HTTPS
  apt-get update
  apt-get install -y ca-certificates curl gnupg lsb-release

  # Get distribution
  DISTRO=$(lsb_release -is | tr '[:upper:]' '[:lower:]')
  echo $DISTRO

  # Add Docker's official GPG key
  curl -fsSL https://download.docker.com/linux/$DISTRO/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

  # Set up the stable Docker repository
  echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/$DISTRO \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

  # Install Docker Engine
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io -y
}

# Function to install AWS CLI
AWSInstall() {
  # Install unzip package
  apt-get install -y unzip

  # Download the AWS CLI version 2 for Linux (64-bit)
  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"

  # Unzip the downloaded AWS CLI package
  unzip awscliv2.zip

  # Run the AWS CLI installation script
  ./aws/install
}

# Function to install Azure CLI
AzureInstall() {
  # Obtain the necessary packages for the installation process
  apt-get update
  apt-get install -y ca-certificates curl apt-transport-https lsb-release gnupg

  # Download and install the Microsoft signing key
  curl -sL https://packages.microsoft.com/keys/microsoft.asc |
      gpg --dearmor |
      tee /etc/apt/trusted.gpg.d/microsoft.gpg > /dev/null

  # Add the Azure CLI repository
  AZ_REPO=$(lsb_release -cs)
  echo "deb [arch=amd64] https://packages.microsoft.com/repos/azure-cli/ $AZ_REPO main" |
      tee /etc/apt/sources.list.d/azure-cli.list

  # Update repository information and install Azure CLI
  apt-get update
  apt-get install -y azure-cli
}

# Function to install jq library
JQInstall() {
  apt-get update
  apt-get install -y jq
}

# Function to install Gcloud CLI
GcloudInstall() {
  apt-get update
  curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
  echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
  apt-get update && apt-get install google-cloud-cli -y
}

InstallTools() {
  # Install tools
  for tool in $TOOLS; do
    echo " - Installing $tool"

    case $tool in
      # Install unzip if it is not installed
      unzip ) command unzip || apt install unzip ;;

      # Install jq dependencies if is not installed
      jq ) command -v jq || JQInstall ;;

      # Install Docker if it is not installed
      docker ) command -v docker || DockerInstall ;;

      # Install AWS CLI if it is not installed
      aws ) command -v aws || AWSInstall ;;

      # Install Azure CLI if it is not installed
      az ) command -v az || AzureInstall ;;

      # Install Gcloud CLI if it is not installed
      gcloud ) command -v gcloud || GcloudInstall ;;

      * ) echo '[Invalid tool]'; Usage; exit 1 ;;
    esac
  done
}

# Define default variables
TOOLS=""

# Parse named parameters
while getopts "t:h" opt; do
  case ${opt} in
    t ) TOOLS="$TOOLS $OPTARG" ;;
    h ) Usage; exit 0 ;;
    \? ) echo '[Invalid parameter]'; Usage; exit 1 ;;
  esac
done

# Check if any tools were specified
if [ -z "$TOOLS" ]; then
  echo "No tools provided."
  Usage
  exit 1
fi

# Install selected tools
InstallTools
