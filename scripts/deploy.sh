#!/bin/bash
set -e

DeployImage() {
  # Load gcp credentials
  sh ./scripts/gcp_login.sh

  # Log in to Artifacts
  gcloud auth configure-docker $REGION-docker.pkg.dev --quiet

  # Push Docker image to AWS
  docker push $REGION-docker.pkg.dev/$PROJECT/$BASE_NAME/$SERVICE:latest
}

DeployBackend() {
  # Build and tag the Docker image
  docker build \
    -f ./Dockerfile \
    -t $REGION-docker.pkg.dev/$PROJECT/$BASE_NAME/$SERVICE:latest \
    app/

  DeployImage

  sed 's|=|: |g' conn/$SERVICE.env > conn/$SERVICE.yaml
  echo "\nDEPLOYMENT_VERSION: $(date +%Y.%m.%d.%H.%M)" >> conn/$SERVICE.yaml

  # Update Cloud run service
  gcloud run deploy \
    $BASE_NAME-$SERVICE \
    --project $PROJECT \
    --image $REGION-docker.pkg.dev/$PROJECT/$BASE_NAME/$SERVICE \
    --platform managed \
    --region $REGION \
    --memory 2Gi \
    --cpi 2 \
    --max 1 \
    --port 80 \
    --timeout 3600 \
    --env-vars-file conn/$SERVICE.yaml \
    --allow-unauthenticated \
    --service-account $BASE_NAME@$PROJECT.iam.gserviceaccount.com

  rm conn/$SERVICE.yaml
}

. ./conn/.env

SERVICE=back
DeployBackend
