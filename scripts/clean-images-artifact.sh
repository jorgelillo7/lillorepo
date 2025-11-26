#!/bin/bash
set -e # El script se detendrá si un comando falla

# --- CONFIGURACIÓN ---
# Repositorio de Artifact Registry
REPO="europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker"

# Imágenes a limpiar con la estrategia "mantener solo la última"
SIMPLE_IMAGES=("web" "scraper_job")

# Imágenes a limpiar con la estrategia "borrar solo las no etiquetadas"
MULTI_ARCH_IMAGES=("python-base")


# --- LÓGICA DE LIMPIEZA PARA IMÁGENES SIMPLES ---
echo "--- Limpiando imágenes simples (manteniendo la más reciente) ---"
for IMAGE in "${SIMPLE_IMAGES[@]}"; do
    echo "[INFO] Limpiando el repositorio: $IMAGE"

    # Obtiene la lista de todos los digests (hashes) ordenados por fecha, del más nuevo al más viejo
    DIGESTS_TO_DELETE=$(gcloud artifacts docker images list "$REPO/$IMAGE" \
        --sort-by=~CREATE_TIME \
        --format="get(digest)" | tail -n +2) # tail -n +2 se salta la primera línea (la más nueva)

    if [ -z "$DIGESTS_TO_DELETE" ]; then
        echo "[OK] No hay imágenes antiguas que borrar para $IMAGE."
        continue
    fi

    for DIGEST in $DIGESTS_TO_DELETE; do
        echo "[ACTION] Borrando imagen antigua: $IMAGE@$DIGEST"
        gcloud artifacts docker images delete "$REPO/$IMAGE@$DIGEST" --delete-tags --quiet
    done
    echo "[OK] Limpieza de $IMAGE completada."
done

echo "" # Línea en blanco para separar

# --- LÓGICA DE LIMPIEZA PARA IMÁGENES MULTI-ARQUITECTURA ---
echo "--- Limpiando imágenes multi-arquitectura (borrando las no etiquetadas) ---"
for IMAGE in "${MULTI_ARCH_IMAGES[@]}"; do
    echo "[INFO] Limpiando el repositorio: $IMAGE"

    # Obtiene solo los digests de las imágenes que NO tienen ninguna etiqueta
    UNTAGGED_DIGESTS=$(gcloud artifacts docker images list "$REPO/$IMAGE" \
        --filter="NOT TAGS:*" \
        --format="get(digest)")

    if [ -z "$UNTAGGED_DIGESTS" ]; then
        echo "[OK] No hay imágenes no etiquetadas que borrar para $IMAGE."
        continue
    fi

    for DIGEST in $UNTAGGED_DIGESTS; do
        echo "[ACTION] Borrando imagen no etiquetada: $IMAGE@$DIGEST"
        gcloud artifacts docker images delete "$REPO/$IMAGE@$DIGEST" --quiet
    done
    echo "[OK] Limpieza de $IMAGE completada."
done

echo ""
echo "--- Limpieza finalizada ---"