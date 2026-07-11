#!/bin/bash
# GCP cost + quota checker for biwenger-tools.
# Covers all dimensions that have a cost or a free-tier cap.
# Robust: each section catches errors and continues.
# Compatible with bash 3 (macOS default).
#
# Drift detection: also surfaces the decisions captured in docs/gcp.md
# (budget amount, log retention, Cloud Run cpu/concurrency/minScale).
# Catches things like Cloud Run silently resetting `--cpu` to 1 when an
# `--image` update is issued without re-passing the flag — happened on
# 2026-05-16 with both bots after a python-base rebuild.

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

# Decisions captured in docs/gcp.md — alert if drifted from these.
EXPECTED_LOG_RETENTION_DAYS=7
EXPECTED_BUDGET_EUR=1

STATUS_OK="OK"
STATUS_WARN="WARN"
STATUS_OVER="OVER"

# Summary variables (no associative arrays — bash 3 compat)
SUM_STORAGE="" SUM_ARTIFACT="" SUM_RUN_SERVICES="" SUM_RUN_JOBS=""
SUM_SECRETS="" SUM_SCHEDULER="" SUM_LOGGING=""
SUM_BUDGET="" SUM_RETENTION="" SUM_RUN_CONFIG=""

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
SECRETS=$(gcloud secrets list --project "$PROJECT" --format="value(name)" 2>/dev/null)
if [ -z "$SECRETS" ]; then
    warn
    SUM_SECRETS="$STATUS_WARN — sin datos"
else
    SECRET_COUNT=$(echo "$SECRETS" | wc -l | tr -d ' ')
    # Billing counts every non-destroyed version — disabled versions still
    # bill. The free tier is 6 *versions*, not 6 secrets.
    TOTAL_VERSIONS=0
    DISABLED_VERSIONS=0
    while IFS= read -r secret; do
        STATES=$(gcloud secrets versions list "$secret" --project "$PROJECT" \
            --format="value(state)" 2>/dev/null)
        BILLABLE=$(echo "$STATES" | grep -ciE 'enabled|disabled')
        DISABLED=$(echo "$STATES" | grep -ci 'disabled')
        TOTAL_VERSIONS=$((TOTAL_VERSIONS + BILLABLE))
        DISABLED_VERSIONS=$((DISABLED_VERSIONS + DISABLED))
        echo "    - $secret: $BILLABLE versiones facturables"
    done <<< "$SECRETS"
    echo "  Secrets: $SECRET_COUNT — versiones facturables: $TOTAL_VERSIONS"
    echo "  Free tier: $FREE_SECRETS versiones (enabled + disabled) gratis / mes"
    if [ "$DISABLED_VERSIONS" -gt 0 ] 2>/dev/null; then
        echo "  💡 $DISABLED_VERSIONS versiones disabled — siguen facturando;"
        echo "     destrúyelas: gcloud secrets versions destroy <v> --secret=<name>"
    fi
    if [ "$TOTAL_VERSIONS" -gt "$FREE_SECRETS" ] 2>/dev/null; then
        SUM_SECRETS="$STATUS_OVER — $TOTAL_VERSIONS versiones (>${FREE_SECRETS} free)"
    else
        SUM_SECRETS="$STATUS_OK — $TOTAL_VERSIONS versiones en $SECRET_COUNT secrets"
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
# Budget alerts (skill recommendation: every project has an active budget)
# ---------------------------
echo "💰 Budget alerts"
BILLING_ACCOUNT=$(gcloud billing projects describe "$PROJECT" \
    --format="value(billingAccountName)" 2>/dev/null | sed 's|billingAccounts/||')
if [ -z "$BILLING_ACCOUNT" ]; then
    warn
    SUM_BUDGET="$STATUS_WARN — sin billing account"
else
    BUDGET_INFO=$(gcloud billing budgets list --billing-account "$BILLING_ACCOUNT" \
        --format="value(amount.specifiedAmount.units,amount.specifiedAmount.currencyCode,displayName)" \
        2>/dev/null | head -1)
    if [ -z "$BUDGET_INFO" ]; then
        echo "  🚨 NO hay budget configurado en la billing account"
        SUM_BUDGET="$STATUS_OVER — sin budget configurado"
    else
        BUDGET_AMOUNT=$(echo "$BUDGET_INFO" | awk '{print $1}')
        BUDGET_CURRENCY=$(echo "$BUDGET_INFO" | awk '{print $2}')
        BUDGET_NAME=$(echo "$BUDGET_INFO" | cut -d$'\t' -f3-)
        echo "  Budget: ${BUDGET_AMOUNT} ${BUDGET_CURRENCY} — '${BUDGET_NAME}'"
        echo "  Esperado: ${EXPECTED_BUDGET_EUR} EUR (ver docs/gcp.md)"
        if [ "$BUDGET_AMOUNT" = "$EXPECTED_BUDGET_EUR" ] && [ "$BUDGET_CURRENCY" = "EUR" ]; then
            SUM_BUDGET="$STATUS_OK — ${BUDGET_AMOUNT} ${BUDGET_CURRENCY}"
        else
            SUM_BUDGET="$STATUS_WARN — ${BUDGET_AMOUNT} ${BUDGET_CURRENCY} (esperado ${EXPECTED_BUDGET_EUR} EUR)"
        fi
    fi
fi
echo

# ---------------------------
# Log retention (decision: 7 days, see docs/gcp.md)
# ---------------------------
echo "📦 Log retention"
LOG_RETENTION=$(gcloud logging buckets describe _Default --location=global \
    --project "$PROJECT" --format="value(retentionDays)" 2>/dev/null)
if [ -z "$LOG_RETENTION" ]; then
    warn
    SUM_RETENTION="$STATUS_WARN — sin datos"
else
    echo "  _Default bucket: ${LOG_RETENTION} días (esperado: ${EXPECTED_LOG_RETENTION_DAYS})"
    if [ "$LOG_RETENTION" -eq "$EXPECTED_LOG_RETENTION_DAYS" ] 2>/dev/null; then
        SUM_RETENTION="$STATUS_OK — ${LOG_RETENTION}d"
    else
        SUM_RETENTION="$STATUS_WARN — ${LOG_RETENTION}d (esperado ${EXPECTED_LOG_RETENTION_DAYS}d)"
    fi
fi
echo

# ---------------------------
# Cloud Run runtime config (detect drift on cpu, concurrency, minScale)
# ---------------------------
echo "📐 Cloud Run runtime config"
if [ -z "$RUN_SERVICES" ]; then
    SUM_RUN_CONFIG="$STATUS_WARN — sin services"
else
    DRIFT=0
    printf "  %-25s %5s %6s %8s\n" "service" "cpu" "conc" "minScale"
    while IFS= read -r svc; do
        [ -z "$svc" ] && continue
        CFG=$(gcloud run services describe "$svc" --region="$REGION" --project "$PROJECT" \
            --format="value(spec.template.spec.containers[0].resources.limits.cpu,spec.template.spec.containerConcurrency,spec.template.metadata.annotations[autoscaling.knative.dev/minScale])" \
            2>/dev/null)
        CPU=$(echo "$CFG" | awk -F'\t' '{print $1}')
        CONC=$(echo "$CFG" | awk -F'\t' '{print $2}')
        MIN=$(echo "$CFG" | awk -F'\t' '{print $3}')
        MIN="${MIN:-0}"
        printf "  %-25s %5s %6s %8s\n" "$svc" "${CPU:-?}" "${CONC:-?}" "$MIN"
        # Flag drift: any service with minScale > 0 (idle cost) or unexpected cpu/concurrency mix
        if [ "$MIN" != "0" ] && [ -n "$MIN" ]; then
            DRIFT=1
        fi
    done <<< "$RUN_SERVICES"
    if [ "$DRIFT" -eq 0 ]; then
        SUM_RUN_CONFIG="$STATUS_OK — todos minScale=0"
    else
        SUM_RUN_CONFIG="$STATUS_WARN — algún service con minScale>0 (idle cost)"
    fi
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
printf "  %-22s %s\n" "Budget alerts"     "$(status_icon "${SUM_BUDGET%% *}") — ${SUM_BUDGET#* — }"
printf "  %-22s %s\n" "Log retention"     "$(status_icon "${SUM_RETENTION%% *}") — ${SUM_RETENTION#* — }"
printf "  %-22s %s\n" "Cloud Run config"  "$(status_icon "${SUM_RUN_CONFIG%% *}") — ${SUM_RUN_CONFIG#* — }"
echo
echo "  ℹ️  Para costes de Cloud Build y Monitoring ver Cloud Console > Billing"
echo "=========================================="
