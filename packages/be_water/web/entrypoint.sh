#!/bin/sh
set -e

# Extract the core package if present (Bazel ships it as a tar to
# preserve directory structure).
if [ -f /app/core_srcs.tar ]; then
    echo ">>> Init: extracting core package..."
    cd /app
    tar -xf core_srcs.tar
    rm -f core_srcs.tar
fi

export PYTHONPATH="/app:${PYTHONPATH}"

echo ">>> Starting be-water..."
exec python3 /app/packages/be_water/web/gunicorn_prod_runner.py
