#!/bin/bash
# Extrae el auth token del bundle JavaScript de un APK de React Native
# sin necesitar Frida ni emulador.
#
# Uso:
#   ./extract_token.sh com.ideatic.jornadaperfecta.apk
#   ./extract_token.sh "Jornada Perfecta_4.2_APKPure.xapk"
#
# Si es un .xapk, primero extrae el APK base:
#   unzip -o app.xapk -d app_splits && ./extract_token.sh app_splits/com.paquete.app.apk
#
# Optional second argument: the known token prefix (the first characters of
# jp_auth_token in biwenger-secrets), to confirm whether the token changed.
# It is an argument, not a constant, because this repository is public.

APK="${1}"
PREFIX="${2}"

if [ -z "$APK" ]; then
    echo "Uso: $0 <archivo.apk>"
    exit 1
fi

if [ ! -f "$APK" ]; then
    echo "Error: no se encuentra el archivo '$APK'"
    exit 1
fi

if [ -n "$PREFIX" ]; then
    echo "=== Buscando token conocido (${PREFIX}…) ==="
    unzip -p "$APK" assets/index.android.bundle | strings | grep -o "${PREFIX}[^ \"&]*"
fi

echo ""
echo "=== Buscando cualquier campo auth/key/token ==="
unzip -p "$APK" assets/index.android.bundle | strings | grep -oE '"(auth|key|token|secret)":"[^"]+"' | sort -u

echo ""
echo "=== Buscando URLs de la API ==="
unzip -p "$APK" assets/index.android.bundle | strings | grep -oE 'https?://[a-zA-Z0-9./_-]+/api/[a-zA-Z0-9./_?=-]+' | sort -u | head -20
