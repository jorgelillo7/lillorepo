#!/bin/sh
set -e

# Extraer el paquete 'core' si está presente en el directorio raíz.
# Esto es necesario porque Bazel lo empaqueta como un archivo .tar para preservar la estructura.
if [ -f /app/core_srcs.tar ]; then
    echo ">>> Inicializando: Extrayendo el paquete core..."
    cd /app
    tar -xf core_srcs.tar
    rm -f core_srcs.tar
fi

# /app es la raíz del proyecto: módulos como `packages.biwenger_tools.web.app`
# y `core.sdk.gcp` resuelven sin trucos.
export PYTHONPATH="/app:${PYTHONPATH}"

echo ">>> Iniciando la aplicación..."
exec python3 /app/packages/biwenger_tools/web/gunicorn_prod_runner.py
