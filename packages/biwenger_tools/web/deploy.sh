#!/bin/bash

# Carga todas las variables desde el archivo .env a la sesión actual de la terminal
source .env

# Ejecuta el comando de despliegue usando las variables cargadas
gcloud run deploy biwenger-summary \
  --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/web \
  --platform managed \
  --region europe-southwest1 \
  --allow-unauthenticated \
  --update-secrets=/gdrive_sa/biwenger-tools-sa.json=biwenger-tools-sa-regional:latest \
  --set-env-vars="LIGAS_ESPECIALES_SHEET_ID_25_26=$LIGAS_ESPECIALES_SHEET_ID_25_26,TROFEOS_SHEET_ID_25_26=$TROFEOS_SHEET_ID_25_26,GCP_PROJECT_ID=$GCP_PROJECT_ID,CLOUD_RUN_JOB_NAME=$CLOUD_RUN_JOB_NAME,CLOUD_RUN_REGION=$CLOUD_RUN_REGION,SECRET_KEY=$SECRET_KEY,ADMIN_PASSWORD=$ADMIN_PASSWORD,TEMPORADA_ACTUAL=$TEMPORADA_ACTUAL"
