#!/bin/bash
# GCP cost + quota checker for biwenger-tools.
# Covers all dimensions that have a cost or a free-tier cap.
# Robust: each section catches errors and continues.
# Compatible with bash 3 (macOS default).

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
FREE_SECRETS=6          # active versions / month
FREE_SCHEDULER=3        # jobs

STATUS_OK="OK"
STATUS_WARN="WARN"
STATUS_OVER="OVER"

# Summary variables (no associative arrays — bash 3 compat)
SUM_STORAGE="" SUM_ARTIFACT="" SUM_RUN_SERVICES="" SUM_RUN_JOBS=""
SUM_SECRETS="" SUM_SCHEDULER="" SUM_LOGGING=""

warn() { echo "  ⚠️  No disponible (revisa permisos / API habilitada)"; }

status_icon() {
    case "$1" in
        OK)   echo "✅ OK"   ;;
        WARN) echo "⚠️  WARN" ;;
        OVER) echo "🚨 OVER" ;;
        *)    echo "❓ $1"   ;;
    esac
}

echo "=== GCP cost check — project: $PROJECT ==="
echo

# ---------------------------
# Cloud Storage
# ---------------------------
echo "💾 Cloud Storage"
STORAGE_USED=$(gcloud storage buckets list --project "$PROJECT" --format="get(sizeGb)" 2>/dev/null \
    | awk '{sum+=$1} END {print sum+0}')
STORAGE_USED="${STORAGE_USED:-0}"
STORAGE_PCT=$(awk "BEGIN {printf \"%.0f\", ($STORAGE_USED/$FREE_STORAGE)*100}")
echo "  Uso: ${STORAGE_USED} GB  (free tier: ${FREE_STORAGE} GB/mes — ${STORAGE_PCT}%)"
if [ "$STORAGE_PCT" -gt 100 ] 2>/dev/null; then
    SUM_STORAGE="$STATUS_OVER — ${STORAGE_USED} GB (>${FREE_STORAGE} GB)"
elif [ "$STORAGE_PCT" -gt 80 ] 2>/dev/null; then
    SUM_STORAGE="$STATUS_WARN — ${STORAGE_USED} GB (${STORAGE_PCT}% del free tier)"
else
    SUM_STORAGE="$STATUS_OK — ${STORAGE_USED} GB"
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
    SUM_ARTIFACT="$STATUS_OVER — ${ARTIFACT_GB} GB (>${FREE_ARTIFACT} GB)"
elif [ "$ARTIFACT_PCT" -gt 80 ] 2>/dev/null; then
    SUM_ARTIFACT="$STATUS_WARN — ${ARTIFACT_GB} GB (${ARTIFACT_PCT}% del free tier)"
else
    SUM_ARTIFACT="$STATUS_OK — ${ARTIFACT_GB} GB"
fi
echo

# ---------------------------
# Cloud Run — Services
# ---------------------------
echo "🚀 Cloud Run Services"
RUN_SERVICES=$(gcloud run services list --project "$PROJECT" --format="value(metadata.name)" 2>/dev/null)
if [ -z "$RUN_SERVICES" ]; then
    warn
    SUM_RUN_SERVICES="$STATUS_WARN — sin datos"
else
    SVC_COUNT=$(echo "$RUN_SERVICES" | wc -l | tr -d ' ')
    echo "  Servicios desplegados ($SVC_COUNT):"
    echo "$RUN_SERVICES" | sed 's/^/    - /'
    echo "  Free tier: 2M requests/mes, 360k vCPU-s, 180k GiB-s (compartido con Jobs)"
    echo "  ℹ️  Para uso real de CPU/memoria ver Cloud Console > Cloud Run > Metrics"
    SUM_RUN_SERVICES="$STATUS_OK — $SVC_COUNT services"
fi
echo

# ---------------------------
# Cloud Run — Jobs
# ---------------------------
echo "⚙️  Cloud Run Jobs"
RUN_JOBS=$(gcloud run jobs list --project "$PROJECT" --format="value(metadata.name)" 2>/dev/null)
if [ -z "$RUN_JOBS" ]; then
    warn
    SUM_RUN_JOBS="$STATUS_WARN — sin datos"
else
    JOB_COUNT=$(echo "$RUN_JOBS" | wc -l | tr -d ' ')
    echo "  Jobs desplegados ($JOB_COUNT):"
    echo "$RUN_JOBS" | sed 's/^/    - /'
    echo "  Ejecuciones recientes:"
    while IFS= read -r job; do
        EXEC_COUNT=$(gcloud run jobs executions list --job "$job" --project "$PROJECT" \
            --region "$REGION" --format="value(metadata.name)" 2>/dev/null | wc -l | tr -d ' ')
        echo "    - $job: ${EXEC_COUNT} ejecuciones (histórico visible)"
    done <<< "$RUN_JOBS"
    SUM_RUN_JOBS="$STATUS_OK — $JOB_COUNT jobs"
fi
echo

# ---------------------------
# Secret Manager
# ---------------------------
echo "🔑 Secret Manager"
SECRET_COUNT=$(gcloud secrets list --project "$PROJECT" --format="value(name)" 2>/dev/null | wc -l | tr -d ' ')
if [ -z "$SECRET_COUNT" ] || [ "$SECRET_COUNT" = "0" ]; then
    warn
    SUM_SECRETS="$STATUS_WARN — sin datos"
else
    echo "  Secrets activos: $SECRET_COUNT"
    echo "  Free tier: $FREE_SECRETS versiones activas gratis / mes"
    echo "  Límite duro del proyecto: 1000 secrets (cap de GCP, no es coste)"
    if [ "$SECRET_COUNT" -gt 8 ] 2>/dev/null; then
        echo "  💡 Más de 8 secrets — considera consolidar en JSON por dominio"
        SUM_SECRETS="$STATUS_WARN — $SECRET_COUNT secrets (>8, considera consolidar)"
    else
        SUM_SECRETS="$STATUS_OK — $SECRET_COUNT secrets"
    fi
fi
echo

# ---------------------------
# Cloud Scheduler
# ---------------------------
echo "🕐 Cloud Scheduler"
SCHED_COUNT=$(gcloud scheduler jobs list --project "$PROJECT" --location "$REGION" \
    --format="value(name)" 2>/dev/null | wc -l | tr -d ' ')
if [ "$SCHED_COUNT" = "0" ]; then
    # Try listing all locations in case region differs
    SCHED_COUNT=$(gcloud scheduler jobs list --project "$PROJECT" \
        --format="value(name)" 2>/dev/null | wc -l | tr -d ' ')
fi
if [ -z "$SCHED_COUNT" ] || [ "$SCHED_COUNT" = "0" ]; then
    warn
    SUM_SCHEDULER="$STATUS_WARN — sin datos"
else
    echo "  Jobs programados: $SCHED_COUNT  (free tier: $FREE_SCHEDULER / mes)"
    if [ "$SCHED_COUNT" -gt "$FREE_SCHEDULER" ] 2>/dev/null; then
        SUM_SCHEDULER="$STATUS_OVER — $SCHED_COUNT jobs (>${FREE_SCHEDULER} free)"
    else
        SUM_SCHEDULER="$STATUS_OK — $SCHED_COUNT jobs"
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
    SUM_LOGGING="$STATUS_WARN — sin datos"
else
    echo "  Log streams: $LOG_COUNT  (proxy — volumen real ver Cloud Console)"
    echo "  Free tier: 50 GB ingest / mes"
    SUM_LOGGING="$STATUS_OK — $LOG_COUNT log streams (ver Console para volumen)"
fi
echo

# ---------------------------
# Resumen final
# ---------------------------
echo "=========================================="
echo "  RESUMEN"
echo "=========================================="
printf "  %-22s %s\n" "Cloud Storage"     "$(status_icon "${SUM_STORAGE%% *}") — ${SUM_STORAGE#* — }"
printf "  %-22s %s\n" "Artifact Registry" "$(status_icon "${SUM_ARTIFACT%% *}") — ${SUM_ARTIFACT#* — }"
printf "  %-22s %s\n" "Cloud Run Services" "$(status_icon "${SUM_RUN_SERVICES%% *}") — ${SUM_RUN_SERVICES#* — }"
printf "  %-22s %s\n" "Cloud Run Jobs"    "$(status_icon "${SUM_RUN_JOBS%% *}") — ${SUM_RUN_JOBS#* — }"
printf "  %-22s %s\n" "Secret Manager"    "$(status_icon "${SUM_SECRETS%% *}") — ${SUM_SECRETS#* — }"
printf "  %-22s %s\n" "Cloud Scheduler"   "$(status_icon "${SUM_SCHEDULER%% *}") — ${SUM_SCHEDULER#* — }"
printf "  %-22s %s\n" "Logging"           "$(status_icon "${SUM_LOGGING%% *}") — ${SUM_LOGGING#* — }"
echo
echo "  ℹ️  Para costes de Cloud Build y Monitoring ver Cloud Console > Billing"
echo "=========================================="
