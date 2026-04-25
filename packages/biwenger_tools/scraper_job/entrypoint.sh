#!/bin/sh
set -e

# Extract the 'core' package if present in the root directory.
# Necessary because Bazel packages it as a .tar to preserve directory structure.
if [ -f /app/core_srcs.tar ]; then
    echo ">>> Initializing: Extracting core package..."
    cd /app
    tar -xf core_srcs.tar
    rm -f core_srcs.tar
fi

export PYTHONPATH="/app:${PYTHONPATH}"

echo ">>> Starting scraper job..."
exec python3 -m packages.biwenger_tools.scraper_job.get_messages
