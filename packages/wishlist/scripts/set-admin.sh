#!/bin/sh
# Set the /admin credentials as Worker secrets. The password is random, never printed,
# and left on the clipboard to save in the Passwords app with the site's address.
#
# Usage: npm run set-admin

set -eu
cd "$(dirname "$0")/.."
WRANGLER=deploy/node_modules/.bin/wrangler

printf '%s' "${ADMIN_USER:-jorge}" | "$WRANGLER" secret put ADMIN_USER >/dev/null
PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
printf '%s' "$PASSWORD" | "$WRANGLER" secret put ADMIN_PASSWORD >/dev/null
printf '%s' "$PASSWORD" | pbcopy
echo "Admin user: ${ADMIN_USER:-jorge}. The password is on the clipboard."
