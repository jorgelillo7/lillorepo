#!/bin/bash
# GCP cost + quota checker for the whole billing account.
# Covers all dimensions that have a cost or a free-tier cap.
# Robust: each section catches errors and continues.
# Compatible with bash 3 (macOS default).
#
# Without flags it audits every project in sequence (biwenger-tools,
# be-water-app) and closes with the billing-account-wide Secret Manager
# check — the 6-version free tier is per BILLING ACCOUNT, not per project.
# Pass --project=X to audit a single project.
#
# Drift detection: also surfaces the decisions captured in docs/gcp.md and
# INFRA.md (budget amount, log retention, Cloud Run cpu/concurrency/minScale).
# Catches things like Cloud Run silently resetting `--cpu` to 1 when an
# `--image` update is issued without re-passing the flag — happened on
# 2026-05-16 with both bots after a python-base rebuild.

ALL_PROJECTS="biwenger-tools be-water-app"
REGION="${REGION:-europe-southwest1}"
# Cloud Scheduler is not offered in europe-southwest1 (Madrid); jobs live in
# the closest supported region instead (see docs/gcp.md).
SCHEDULER_REGION="${SCHEDULER_REGION:-europe-west1}"

# Parse optional --project=X flag
PROJECT="${PROJECT:-}"
for arg in "$@"; do
    case $arg in
        --project=*) PROJECT="${arg#*=}" ;;
        --region=*)  REGION="${arg#*=}" ;;
    esac
done

FREE_STORAGE=5          # GB / month — always-free ONLY in us-east1/us-west1/us-central1
FREE_ARTIFACT=0.5       # GB / month
FREE_SECRETS=6          # active versions / month — per BILLING ACCOUNT
FREE_SCHEDULER=3        # jobs

# Decisions captured in docs/gcp.md — alert if drifted from these.
EXPECTED_LOG_RETENTION_DAYS=7
EXPECTED_BUDGET_EUR=1

STATUS_OK="OK"
STATUS_WARN="WARN"
STATUS_OVER="OVER"

status_icon() {
    case "$1" in
        OK)   echo "✅ OK"   ;;
        WARN) echo "⚠️  WARN" ;;
        OVER) echo "🚨 OVER" ;;
        *)    echo "❓ $1"   ;;
    esac
}

count_billable_versions() {
    # Billing counts every non-destroyed version — disabled versions still
    # bill. Prints "<billable> <disabled>" for the given project.
    local project="$1" total=0 disabled=0 secret states
    while IFS= read -r secret; do
        [ -z "$secret" ] && continue
        states=$(gcloud secrets versions list "$secret" --project "$project" \
            --format="value(state)" 2>/dev/null)
        total=$((total + $(echo "$states" | grep -ciE 'enabled|disabled')))
        disabled=$((disabled + $(echo "$states" | grep -ci 'disabled')))
    done <<< "$(gcloud secrets list --project "$project" --format="value(name)" 2>/dev/null)"
    echo "$total $disabled"
}

# ---------------------------------------------------------------------------
# Multi-project mode: recurse per project, then the account-wide checks.
# ---------------------------------------------------------------------------
if [ -z "$PROJECT" ]; then
    for p in $ALL_PROJECTS; do
        bash "$0" --project="$p" --region="$REGION"
        echo
    done

    echo "=== Billing account — Secret Manager total ==="
    echo "  (free tier: ${FREE_SECRETS} versiones por CUENTA, no por proyecto)"
    ACCOUNT_VERSIONS=0
    for p in $ALL_PROJECTS; do
        set -- $(count_billable_versions "$p")
        echo "    - $p: $1 versiones facturables ($2 disabled)"
        ACCOUNT_VERSIONS=$((ACCOUNT_VERSIONS + $1))
    done
    if [ "$ACCOUNT_VERSIONS" -gt "$FREE_SECRETS" ]; then
        echo "  🚨 OVER — $ACCOUNT_VERSIONS versiones en la cuenta (>${FREE_SECRETS} free)"
    else
        echo "  ✅ OK — $ACCOUNT_VERSIONS/${FREE_SECRETS} versiones en la cuenta"
    fi
    exit 0
fi

# ---------------------------------------------------------------------------
# Single-project audit. Both projects run Cloud Run jobs + a Scheduler
# trigger; be-water-app additionally owns the Gemini prepaid-credit check
# (be_water studio photos).
# ---------------------------------------------------------------------------
case "$PROJECT" in
    be-water-app) HAS_GEMINI=1 ;;
    *)            HAS_GEMINI=0 ;;
esac

# Summary variables (no associative arrays — bash 3 compat)
SUM_STORAGE="" SUM_ARTIFACT="" SUM_RUN_SERVICES="" SUM_RUN_JOBS=""
SUM_SECRETS="" SUM_SCHEDULER="" SUM_LOGGING="" SUM_FIRESTORE=""
SUM_BUDGET="" SUM_RETENTION="" SUM_RUN_CONFIG="" SUM_GEMINI=""

warn() { echo "  ⚠️  No disponible (revisa permisos / API habilitada)"; }

echo "=== GCP cost check — project: $PROJECT ==="
echo

# ---------------------------
# Cloud Storage
# ---------------------------
echo "💾 Cloud Storage"
BUCKETS=$(gcloud storage buckets list --project "$PROJECT" \
    --format="value(name,location)" 2>/dev/null)
if [ -z "$BUCKETS" ]; then
    echo "  Sin buckets."
    SUM_STORAGE="$STATUS_OK — sin buckets"
else
    TOTAL_BYTES=0
    NON_US=0
    while IFS=$'\t' read -r bucket location; do
        [ -z "$bucket" ] && continue
        BYTES=$(gcloud storage du -s "gs://$bucket" 2>/dev/null | awk '{print $1+0}')
        BYTES="${BYTES:-0}"
        TOTAL_BYTES=$((TOTAL_BYTES + BYTES))
        BUCKET_GB=$(awk "BEGIN {printf \"%.3f\", $BYTES/1024/1024/1024}")
        case "$location" in
            US-EAST1|US-WEST1|US-CENTRAL1)
                echo "    - $bucket ($location): ${BUCKET_GB} GB — dentro del always-free US" ;;
            *)
                echo "    - $bucket ($location): ${BUCKET_GB} GB — ⚠️  SIN free tier (solo regiones US)"
                NON_US=1 ;;
        esac
    done <<< "$BUCKETS"
    STORAGE_GB=$(awk "BEGIN {printf \"%.3f\", $TOTAL_BYTES/1024/1024/1024}")
    STORAGE_PCT=$(awk "BEGIN {printf \"%.0f\", ($STORAGE_GB/$FREE_STORAGE)*100}")
    echo "  Total: ${STORAGE_GB} GB  (always-free US: ${FREE_STORAGE} GB/mes — ${STORAGE_PCT}%)"
    if [ "$NON_US" -eq 1 ]; then
        SUM_STORAGE="$STATUS_WARN — ${STORAGE_GB} GB con bucket(s) fuera del free tier"
    elif [ "$STORAGE_PCT" -gt 80 ] 2>/dev/null; then
        SUM_STORAGE="$STATUS_WARN — ${STORAGE_GB} GB (${STORAGE_PCT}% del free tier)"
    else
        SUM_STORAGE="$STATUS_OK — ${STORAGE_GB} GB"
    fi
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
# Firestore
# ---------------------------
echo "🔥 Firestore"
FS_DBS=$(gcloud firestore databases list --project "$PROJECT" \
    --format="value(name,locationId)" 2>/dev/null)
if [ -z "$FS_DBS" ]; then
    warn
    SUM_FIRESTORE="$STATUS_WARN — sin datos"
else
    FS_COUNT=$(echo "$FS_DBS" | wc -l | tr -d ' ')
    echo "$FS_DBS" | sed 's/^/    - /'
    echo "  Free tier (por proyecto): 1 GiB storage, 50k reads / 20k writes al día"
    SUM_FIRESTORE="$STATUS_OK — $FS_COUNT database(s)"
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
    set -- $(count_billable_versions "$PROJECT")
    TOTAL_VERSIONS=$1
    DISABLED_VERSIONS=$2
    echo "$SECRETS" | sed 's/^/    - /'
    echo "  Secrets: $SECRET_COUNT — versiones facturables: $TOTAL_VERSIONS"
    echo "  Free tier: $FREE_SECRETS versiones (enabled + disabled) / mes POR CUENTA"
    echo "  ℹ️  El total de la cuenta se comprueba al final (modo sin --project)"
    if [ "$DISABLED_VERSIONS" -gt 0 ] 2>/dev/null; then
        echo "  💡 $DISABLED_VERSIONS versiones disabled — siguen facturando;"
        echo "     destrúyelas: gcloud secrets versions destroy <v> --secret=<name>"
    fi
    SUM_SECRETS="$STATUS_OK — $TOTAL_VERSIONS versiones en $SECRET_COUNT secrets"
fi
echo

# ---------------------------
# Cloud Scheduler
# ---------------------------
echo "🕐 Cloud Scheduler (región: $SCHEDULER_REGION)"
SCHED_JOBS=$(gcloud scheduler jobs list --project "$PROJECT" --location "$SCHEDULER_REGION" \
    --format="value(name.basename(),state)" 2>/dev/null)
if [ -z "$SCHED_JOBS" ]; then
    warn
    SUM_SCHEDULER="$STATUS_WARN — sin datos"
else
    SCHED_COUNT=$(echo "$SCHED_JOBS" | wc -l | tr -d ' ')
    echo "$SCHED_JOBS" | sed 's/^/    - /'
    echo "  Jobs programados: $SCHED_COUNT  (free tier: $FREE_SCHEDULER por cuenta)"
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
# Budgets live on the billing account; match this project's number in the
# budget filter, falling back to an account-wide budget (no filter).
# ---------------------------
echo "💰 Budget alerts"
BILLING_ACCOUNT=$(gcloud billing projects describe "$PROJECT" \
    --format="value(billingAccountName)" 2>/dev/null | sed 's|billingAccounts/||')
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" \
    --format="value(projectNumber)" 2>/dev/null)
if [ -z "$BILLING_ACCOUNT" ]; then
    warn
    SUM_BUDGET="$STATUS_WARN — sin billing account"
else
    BUDGETS=$(gcloud billing budgets list --billing-account "$BILLING_ACCOUNT" \
        --format="value(displayName,amount.specifiedAmount.units,amount.specifiedAmount.currencyCode,budgetFilter.projects)" \
        2>/dev/null)
    BUDGET_INFO=$(echo "$BUDGETS" | grep "projects/$PROJECT_NUMBER" | head -1)
    if [ -z "$BUDGET_INFO" ]; then
        # No project-scoped budget — an account-wide one (empty filter) counts.
        BUDGET_INFO=$(echo "$BUDGETS" | awk -F'\t' '$4 == "" {print; exit}')
    fi
    if [ -z "$BUDGET_INFO" ]; then
        echo "  🚨 NO hay budget que cubra este proyecto"
        SUM_BUDGET="$STATUS_OVER — sin budget configurado"
    else
        BUDGET_NAME=$(echo "$BUDGET_INFO" | awk -F'\t' '{print $1}')
        BUDGET_AMOUNT=$(echo "$BUDGET_INFO" | awk -F'\t' '{print $2}')
        BUDGET_CURRENCY=$(echo "$BUDGET_INFO" | awk -F'\t' '{print $3}')
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
# Gemini API prepaid credits (be_water studio photos)
# The prepaid balance has NO public API — this section verifies what is
# scriptable (billing link + dedicated budget on the AI Studio project)
# and points at the only place the balance is visible.
# ---------------------------
if [ "$HAS_GEMINI" -eq 1 ]; then
    echo "🍌 Gemini API (créditos prepago — estudio de fotos be_water)"
    GEMINI_PROJECT="gen-lang-client-0059905191"  # AI Studio project "Be Water"
    GEMINI_BILLING=$(gcloud billing projects describe "$GEMINI_PROJECT" \
        --format="value(billingEnabled)" 2>/dev/null)
    if [ "$GEMINI_BILLING" = "True" ]; then
        echo "  Billing vinculado: sí ✅ (proyecto ${GEMINI_PROJECT})"
        SUM_GEMINI="$STATUS_OK — billing ok; saldo: revisar manualmente"
    else
        echo "  🚨 Billing NO vinculado — el estudio de fotos fallará con 429"
        SUM_GEMINI="$STATUS_WARN — sin billing en ${GEMINI_PROJECT}"
    fi
    GEMINI_BUDGET=$(gcloud billing budgets list --billing-account "$BILLING_ACCOUNT" \
        --filter='displayName:gemini' --format="value(displayName)" 2>/dev/null | head -1)
    if [ -n "$GEMINI_BUDGET" ]; then
        echo "  Budget dedicado: '${GEMINI_BUDGET}' ✅"
    else
        echo "  ⚠️  Sin budget dedicado para el proyecto Gemini"
    fi
    echo "  Saldo prepago (sin API — revisar a mano): https://aistudio.google.com/billing"
    echo "  Modelo: prepago = tope duro (0 créditos → 429, imposible sobregastar)"
    echo "  Coste por foto de estudio ≈ \$0.04 (gemini-2.5-flash-image)"
    echo
fi

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
echo "  RESUMEN — $PROJECT"
echo "=========================================="
printf "  %-22s %s\n" "Cloud Storage"     "$(status_icon "${SUM_STORAGE%% *}") — ${SUM_STORAGE#* — }"
printf "  %-22s %s\n" "Artifact Registry" "$(status_icon "${SUM_ARTIFACT%% *}") — ${SUM_ARTIFACT#* — }"
printf "  %-22s %s\n" "Cloud Run Services" "$(status_icon "${SUM_RUN_SERVICES%% *}") — ${SUM_RUN_SERVICES#* — }"
printf "  %-22s %s\n" "Cloud Run Jobs"    "$(status_icon "${SUM_RUN_JOBS%% *}") — ${SUM_RUN_JOBS#* — }"
printf "  %-22s %s\n" "Firestore"         "$(status_icon "${SUM_FIRESTORE%% *}") — ${SUM_FIRESTORE#* — }"
printf "  %-22s %s\n" "Secret Manager"    "$(status_icon "${SUM_SECRETS%% *}") — ${SUM_SECRETS#* — }"
printf "  %-22s %s\n" "Cloud Scheduler"   "$(status_icon "${SUM_SCHEDULER%% *}") — ${SUM_SCHEDULER#* — }"
printf "  %-22s %s\n" "Logging"           "$(status_icon "${SUM_LOGGING%% *}") — ${SUM_LOGGING#* — }"
printf "  %-22s %s\n" "Budget alerts"     "$(status_icon "${SUM_BUDGET%% *}") — ${SUM_BUDGET#* — }"
if [ "$HAS_GEMINI" -eq 1 ]; then
printf "  %-22s %s\n" "Gemini prepago"    "$(status_icon "${SUM_GEMINI%% *}") — ${SUM_GEMINI#* — }"
fi
printf "  %-22s %s\n" "Log retention"     "$(status_icon "${SUM_RETENTION%% *}") — ${SUM_RETENTION#* — }"
printf "  %-22s %s\n" "Cloud Run config"  "$(status_icon "${SUM_RUN_CONFIG%% *}") — ${SUM_RUN_CONFIG#* — }"
echo
echo "  ℹ️  Para costes de Cloud Build y Monitoring ver Cloud Console > Billing"
echo "=========================================="
