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

# Asegurar que Python pueda encontrar todos los módulos necesarios.
# Se añade la raíz del proyecto, el paquete core y el directorio de la aplicación web.
export PYTHONPATH="/app:/app/core:/app/packages/biwenger_tools/web:${PYTHONPATH}"

# Cambiar al directorio de la aplicación web antes de iniciar el servidor.
cd /app/packages/biwenger_tools/web

# Iniciar el servidor Gunicorn.
# 'exec' reemplaza el proceso del shell con el de Gunicorn, lo cual es una buena práctica.
echo ">>> Iniciando la aplicación..."
exec python3 gunicorn_prod_runner.py
