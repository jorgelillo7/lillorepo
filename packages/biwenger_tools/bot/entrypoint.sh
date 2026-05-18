#!/bin/sh
set -e

if [ -f /app/core_srcs.tar ]; then
    echo ">>> Inicializando: Extrayendo el paquete core..."
    cd /app
    tar -xf core_srcs.tar
    rm -f core_srcs.tar
fi

export PYTHONPATH="/app:${PYTHONPATH}"

echo ">>> Iniciando la aplicación..."
exec python3 /app/packages/biwenger_tools/bot/gunicorn_prod_runner.py
