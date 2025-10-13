#!/bin/bash

PROJECT="biwenger-tools"
FREE_STORAGE=5          # GB
FREE_ARTIFACT=0.5       # GB

echo "=== Estimación de costes para el proyecto $PROJECT ==="
echo

# ---------------------------
# Cloud Storage
# ---------------------------
STORAGE_USED=$(gcloud storage buckets list --project $PROJECT --format="get(sizeGb)" | awk '{sum+=$1} END {print sum+0}')
echo "💾 Cloud Storage:"
echo "  Uso: ${STORAGE_USED} GB"
echo "  Free Tier: ${FREE_STORAGE} GB / mes"
echo

# ---------------------------
# Artifact Registry
# ---------------------------
ARTIFACT_USED=$(gcloud artifacts repositories list --project $PROJECT --format="get(sizeBytes)" | awk '{sum+=$1} END {printf "%.2f", sum/1024/1024/1024}')
ARTIFACT_PERCENT=$(awk "BEGIN {printf \"%.0f\", ($ARTIFACT_USED/$FREE_ARTIFACT)*100}")

echo "🖼 Artifact Registry (Docker):"
echo "  Uso: ${ARTIFACT_USED} GB (${ARTIFACT_PERCENT}%)"
echo "  Free Tier: ${FREE_ARTIFACT} GB / mes"
echo