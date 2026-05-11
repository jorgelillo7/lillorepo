#!/bin/bash
# GCP cost + quota checker for biwenger-tools.
# Covers all dimensions that have a cost or a free-tier cap.
# Robust: each section catches errors and continues.

PROJECT="${PROJECT:-biwenger-tools}"
REGION="${REGION:-europe-southwest1}"

# Parse optional --project=X flag
for arg in "$@"; do
    case $arg in
        --project=*) PROJECT="${arg#*=}" ;;
        --region=*)  REGION="${arg#*=}" ;;
    esac
done

FREE_STORAGE=5          # GB / month
FREE_ARTIFACT=0.5       # GB / month
FREE_RUN_REQUESTS=2000000   # requests / month (shared Run+Jobs)
FREE_SECRETS=6          # active versions / month
FREE_SCHEDULER=3        # jobs

STATUS_OK="✅ OK"
STATUS_WARN="⚠️  WARN"
STATUS_OVER="🚨 OVER"

declare -A SUMMARY

warn() { echo "  ⚠️  No disponible (revisa permisos / API habilitada)"; }

echo "=== GCP cost check — project: $PROJECT ==="
echo

# ---------------------------
# Cloud Storage
# ---------------------------
echo "💾 Cloud Storage"
STORAGE_USED=$(gcloud storage buckets list --project "$PROJECT" --format="get(sizeGb)" 2>/dev/null \
    | awk '{sum+=$1} END {print sum+0}')
if [ -z "$STORAGE_USED" ] || [ "$STORAGE_USED" = "0" ]; then
    STORAGE_USED=0
fi
STORAGE_PCT=$(awk "BEGIN {printf \"%.0f\", ($STORAGE_USED/$FREE_STORAGE)*100}")
echo "  Uso: ${STORAGE_USED} GB  (free tier: ${FREE_STORAGE} GB/mes — ${STORAGE_PCT}%)"
if [ "$STORAGE_PCT" -gt 100 ] 2>/dev/null; then
    SUMMARY[storage]="$STATUS_OVER — ${STORAGE_USED} GB (>${FREE_STORAGE} GB)"
elif [ "$STORAGE_PCT" -gt 80 ] 2>/dev/null; then
    SUMMARY[storage]="$STATUS_WARN — ${STORAGE_USED} GB (${STORAGE_PCT}% del free tier)"
else
    SUMMARY[storage]="$STATUS_OK — ${STORAGE_USED} GB"
fi
echo

# ---------------------------
# Artifact Registry
# ---------------------------
echo "🖼  Artifact Registry"
ARTIFACT_BYTES=$(gcloud artifacts repositories list --project "$PROJECT" --format="get(sizeBytes)" 2>/dev/null \
    | awk '{sum+=$1} END {print sum+0}')
if [ -z "$ARTIFACT_BYTES" ] || [ "$ARTIFACT_BYTES" = "0" ]; then
    ARTIFACT_GB=0
else
    ARTIFACT_GB=$(awk "BEGIN {printf \"%.3f\", $ARTIFACT_BYTES/1024/1024/1024}")
fi
ARTIFACT_PCT=$(awk "BEGIN {printf \"%.0f\", ($ARTIFACT_GB/$FREE_ARTIFACT)*100}")
echo "  Uso: ${ARTIFACT_GB} GB  (free tier: ${FREE_ARTIFACT} GB — ${ARTIFACT_PCT}%)"
if [ "$ARTIFACT_PCT" -gt 100 ] 2>/dev/null; then
    SUMMARY[artifact]="$STATUS_OVER — ${ARTIFACT_GB} GB (>${FREE_ARTIFACT} GB)"
elif [ "$ARTIFACT_PCT" -gt 80 ] 2>/dev/null; then
    SUMMARY[artifact]="$STATUS_WARN — ${ARTIFACT_GB} GB (${ARTIFACT_PCT}% del free tier)"
else
    SUMMARY[artifact]="$STATUS_OK — ${ARTIFACT_GB} GB"
fi
echo

# ---------------------------
# Cloud Run — Services
# ---------------------------
echo "🚀 Cloud Run Services"
RUN_SERVICES=$(gcloud run services list --project "$PROJECT" --format="value(metadata.name)" 2>/dev/null)
if [ -z "$RUN_SERVICES" ]; then
    warn
    SUMMARY[run_services]="$STATUS_WARN — sin datos"
else
    SVC_COUNT=$(echo "$RUN_SERVICES" | wc -l | tr -d ' ')
    echo "  Servicios desplegados ($SVC_COUNT):"
    echo "$RUN_SERVICES" | sed 's/^/    - /'
    echo "  Free tier: 2M requests/mes, 360k vCPU-s, 180k GiB-s (compartido con Jobs)"
    echo "  ℹ️  Para uso real de CPU/memoria ver Cloud Console > Cloud Run > Metrics"
    SUMMARY[run_services]="$STATUS_OK — $SVC_COUNT services"
fi
echo

# ---------------------------
# Cloud Run — Jobs
# ---------------------------
echo "⚙️  Cloud Run Jobs"
RUN_JOBS=$(gcloud run jobs list --project "$PROJECT" --format="value(metadata.name)" 2>/dev/null)
if [ -z "$RUN_JOBS" ]; then
    warn
    SUMMARY[run_jobs]="$STATUS_WARN — sin datos"
else
    JOB_COUNT=$(echo "$RUN_JOBS" | wc -l | tr -d ' ')
    echo "  Jobs desplegados ($JOB_COUNT):"
    echo "$RUN_JOBS" | sed 's/^/    - /'
    # Count recent executions for each job (last 30 days)
    echo "  Ejecuciones recientes:"
    while IFS= read -r job; do
        EXEC_COUNT=$(gcloud run jobs executions list --job "$job" --project "$PROJECT" \
            --format="value(metadata.name)" 2>/dev/null | wc -l | tr -d ' ')
        echo "    - $job: ${EXEC_COUNT} ejecuciones (histórico visible)"
    done <<< "$RUN_JOBS"
    SUMMARY[run_jobs]="$STATUS_OK — $JOB_COUNT jobs"
fi
echo

# ---------------------------
# Secret Manager
# ---------------------------
echo "🔑 Secret Manager"
SECRET_COUNT=$(gcloud secrets list --project "$PROJECT" --format="value(name)" 2>/dev/null | wc -l | tr -d ' ')
if [ -z "$SECRET_COUNT" ] || [ "$SECRET_COUNT" = "0" ]; then
    warn
    SUMMARY[secrets]="$STATUS_WARN — sin datos"
else
    echo "  Secrets activos: $SECRET_COUNT"
    echo "  Free tier: $FREE_SECRETS versiones activas gratis / mes"
    echo "  Límite duro del proyecto: 1000 secrets (cap de GCP, no es coste)"
    if [ "$SECRET_COUNT" -gt 8 ] 2>/dev/null; then
        echo "  💡 Más de 8 secrets — considera consolidar en JSON por dominio"
        SUMMARY[secrets]="$STATUS_WARN — $SECRET_COUNT secrets (>8, considera consolidar)"
    else
        SUMMARY[secrets]="$STATUS_OK — $SECRET_COUNT secrets"
    fi
fi
echo

# ---------------------------
# Cloud Scheduler
# ---------------------------
echo "🕐 Cloud Scheduler"
SCHED_COUNT=$(gcloud scheduler jobs list --project "$PROJECT" --location "$REGION" \
    --format="value(name)" 2>/dev/null | wc -l | tr -d ' ')
if [ -z "$SCHED_COUNT" ] || [ "$SCHED_COUNT" = "0" ]; then
    # Try without --location in case region differs
    SCHED_COUNT=$(gcloud scheduler jobs list --project "$PROJECT" \
        --format="value(name)" 2>/dev/null | wc -l | tr -d ' ')
fi
if [ -z "$SCHED_COUNT" ] || [ "$SCHED_COUNT" = "0" ]; then
    warn
    SUMMARY[scheduler]="$STATUS_WARN — sin datos"
else
    echo "  Jobs programados: $SCHED_COUNT  (free tier: $FREE_SCHEDULER / mes)"
    if [ "$SCHED_COUNT" -gt "$FREE_SCHEDULER" ] 2>/dev/null; then
        SUMMARY[scheduler]="$STATUS_OVER — $SCHED_COUNT jobs (>${FREE_SCHEDULER} free)"
    else
        SUMMARY[scheduler]="$STATUS_OK — $SCHED_COUNT jobs"
    fi
fi
echo

# ---------------------------
# Logging
# ---------------------------
echo "📋 Cloud Logging"
LOG_COUNT=$(gcloud logging logs list --project "$PROJECT" 2>/dev/null | wc -l | tr -d ' ')
if [ -z "$LOG_COUNT" ] || [ "$LOG_COUNT" = "0" ]; then
    warn
    SUMMARY[logging]="$STATUS_WARN — sin datos"
else
    echo "  Log streams: $LOG_COUNT  (proxy — volumen real ver Cloud Console)"
    echo "  Free tier: 50 GB ingest / mes"
    SUMMARY[logging]="$STATUS_OK — $LOG_COUNT log streams (ver Console para volumen)"
fi
echo

# ---------------------------
# Resumen final
# ---------------------------
echo "=========================================="
echo "  RESUMEN"
echo "=========================================="
printf "  %-22s %s\n" "Cloud Storage"    "${SUMMARY[storage]:-N/A}"
printf "  %-22s %s\n" "Artifact Registry" "${SUMMARY[artifact]:-N/A}"
printf "  %-22s %s\n" "Cloud Run Services" "${SUMMARY[run_services]:-N/A}"
printf "  %-22s %s\n" "Cloud Run Jobs"   "${SUMMARY[run_jobs]:-N/A}"
printf "  %-22s %s\n" "Secret Manager"   "${SUMMARY[secrets]:-N/A}"
printf "  %-22s %s\n" "Cloud Scheduler"  "${SUMMARY[scheduler]:-N/A}"
printf "  %-22s %s\n" "Logging"          "${SUMMARY[logging]:-N/A}"
echo
echo "  ℹ️  Para costes de Cloud Build y Monitoring ver Cloud Console > Billing"
echo "=========================================="
