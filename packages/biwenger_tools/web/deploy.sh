#!/bin/bash

# Carga todas las variables desde el archivo .env a la sesión actual de la terminal
source .env

# Ejecuta el comando de despliegue usando las variables cargadas.
# Los argumentos extra se reenvían a gcloud: `./deploy.sh --no-traffic --tag preview`
# despliega una revisión de preview sin tocar el tráfico de producción.
gcloud run deploy biwenger-summary \
  --image europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/web \
  --platform managed \
  --region europe-southwest1 \
  --allow-unauthenticated \
  --update-secrets=/gdrive_sa/biwenger-tools-sa.json=biwenger-tools-sa-regional:latest \
  --set-env-vars="TROFEOS_SHEET_ID_25_26=$TROFEOS_SHEET_ID_25_26,H2H_SHEET_ID_26_27=$H2H_SHEET_ID_26_27,GCP_PROJECT_ID=$GCP_PROJECT_ID,CLOUD_RUN_JOB_NAME=$CLOUD_RUN_JOB_NAME,CLOUD_RUN_REGION=$CLOUD_RUN_REGION,SECRET_KEY=$SECRET_KEY,ADMIN_PASSWORD=$ADMIN_PASSWORD,TEMPORADA_ACTUAL=$TEMPORADA_ACTUAL" \
  "$@"
