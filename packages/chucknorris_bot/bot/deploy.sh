#!/bin/bash
# Redeploy chucknorris-bot with a locally pushed image.
#
# Only the image and the version stamp change: the chucknorris-secrets mount,
# env vars and resources stay as the last CI deploy left them. Extra arguments
# go straight to gcloud.
set -euo pipefail

gcloud run deploy chucknorris-bot \
  --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/chucknorris_bot \
  --region europe-southwest1 \
  --project biwenger-tools \
  --update-env-vars="GIT_COMMIT=$(git rev-parse --short HEAD),DEPLOY_TIME=$(TZ=Europe/Madrid date '+%d/%m/%Y %H:%M')" \
  "$@"
