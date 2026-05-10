#!/bin/bash

source .env

gcloud run deploy chucknorris-bot \
  --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/chucknorris_bot \
  --platform managed \
  --region europe-southwest1 \
  --allow-unauthenticated \
  --set-env-vars="TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN,TELEGRAM_WEBHOOK_SECRET=$TELEGRAM_WEBHOOK_SECRET"
