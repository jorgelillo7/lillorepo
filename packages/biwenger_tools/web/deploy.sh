#!/bin/bash
# Redeploy biwenger-summary with a locally pushed image.
#
# Only the image and the version stamp change: secrets, env vars and resources
# stay as the last CI deploy left them. Creating the service from zero is
# DEPLOY_YOUR_OWN.md. Extra arguments go straight to gcloud, so
# `./deploy.sh --no-traffic --tag preview` publishes a preview revision.
set -euo pipefail

gcloud run deploy biwenger-summary \
  --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/web \
  --region europe-southwest1 \
  --project biwenger-tools \
  --update-env-vars="GIT_COMMIT=$(git rev-parse --short HEAD),DEPLOY_TIME=$(TZ=Europe/Madrid date '+%d/%m/%Y %H:%M')" \
  "$@"
