# Intercepting HTTPS Traffic from an Android App with Frida

Complete guide for the process used to discover the Jornada Perfecta private API.
Reproducible for any Android app using certificate pinning.

## Context

Jornada Perfecta (jornadaperfecta.com) has a mobile-only app (iOS/Android) with AI-powered
player prediction scores for fantasy football. The public website does not expose this data.
Using this process we obtained the full endpoint, auth token and response structure.

**Result:** `GET https://www.jornadaperfecta.com/api/fitness-daily?auth=lks9k2k$iJK&...`

See full implementation plan in `.claude/plans/teams_analyzer_rewrite.md`.

---

## Requirements

- Mac Apple Silicon (M1/M2/M3) — guide written for ARM64
- Android Studio installed
- Python 3 with pip3
- The APK/XAPK file of the app to intercept

### Install tools

```bash
# Frida (interceptor)
pip3 install frida-tools

# Add adb to PATH (if not already there)
echo 'export PATH="$PATH:$HOME/Library/Android/sdk/platform-tools"' >> ~/.zshrc
source ~/.zshrc

# Verify
adb version
frida-ps --version   # binary lives in /Library/Frameworks/Python.framework/Versions/3.12/bin/
```

If `frida-ps` is not in PATH:
```bash
export PATH="$PATH:/Library/Frameworks/Python.framework/Versions/3.12/bin"
```

---

## Step 1 — Create the Android emulator

In Android Studio → **Device Manager** → **"+"** → **Create Virtual Device**:

- Hardware: Pixel 6 (or any phone)
- System Image: **API 33 "Tiramisu" · Google APIs · ARM 64 v8a** ← important
  - Google APIs = yes
  - Google Play Store = NO (prevents rooting)
  - ARM 64 v8a = required on M1

> **Why API 33 and not newer?**
> API 37 also works but we hit ABI compatibility issues with this specific app
> (React Native + Hermes, only armeabi-v7a native libs). API 33 solved the problem.

Start the emulator and wait for the home screen.

---

## Step 2 — Prepare the emulator

```bash
# Root it
adb root
adb shell whoami   # should print: root

# Check supported ABIs
adb shell getprop ro.product.cpu.abilist
```

---

## Step 3 — Install the APK

### If it's a .xapk (APKPure)

`.xapk` files are a ZIP containing APK splits. Extract and install:

```bash
unzip -o "AppName.xapk" -d app_apk
cd app_apk
# Install base APK + language + screen density (WITHOUT the ABI split)
adb install-multiple com.package.app.apk config.es.apk config.xxhdpi.apk
```

> If the app uses React Native + Hermes and only has armeabi-v7a libs, install without
> the ABI split. If it crashes with `libhermes.so not found`, see troubleshooting below.

### If it's a universal .apk (Uptodown, etc.)

```bash
adb install app.apk
```

---

## Step 4 — Install and start Frida server

Download the Frida server version matching `frida --version`:

```bash
FRIDA_VERSION=$(python3 -c "import frida; print(frida.__version__)")
echo "Version: $FRIDA_VERSION"

# Download frida-server for android-arm64
curl -L "https://github.com/frida/frida/releases/download/${FRIDA_VERSION}/frida-server-${FRIDA_VERSION}-android-arm64.xz" \
  -o frida-server.xz
xz -d frida-server.xz

# Push to emulator and set permissions
adb push frida-server /data/local/tmp/frida-server
adb shell chmod 755 /data/local/tmp/frida-server

# Start in background
adb shell "nohup /data/local/tmp/frida-server > /dev/null 2>&1 &"

# Verify it can list processes
frida-ps -U | head -10
```

The binary downloaded during this session is at `~/Desktop/frida-server` (ARM64, v17.9.3).

---

## Step 5 — Launch the app with the interceptor

The intercept script is at `scripts/jp_intercept.js` (alongside this document).
It does three things:
1. SSL pinning bypass (TrustManager + OkHttp3 CertificatePinner)
2. Hook `RealCall.execute/enqueue` to capture all OkHttp3 requests
3. Log URL, headers and body for both request and response

```bash
frida -U -f com.package.app \
  -l /path/to/jp_intercept.js
```

For Jornada Perfecta:
```bash
frida -U -f com.ideatic.jornadaperfecta \
  -l docs/technical/reverse-engineering/scripts/jp_intercept.js
```

The app launches in the emulator with the interceptor active. Every HTTPS request
appears in plain text in the terminal.

---

## Step 6 — Capture the request

1. Navigate in the emulator to the screen that triggers the request of interest
2. Watch the terminal output — each request shows:
   - Full URL with query parameters
   - Request headers
   - Request body (if POST)
   - HTTP response status and body

---

## Step 7 — Extract the token from the APK (no Frida needed)

If the token is hardcoded in the React Native JS bundle:

```bash
# Search by known token prefix
unzip -p app.apk assets/index.android.bundle | strings | grep -o 'lks9k2k[^ "&]*'

# Search by generic auth field pattern
unzip -p app.apk assets/index.android.bundle | strings | grep -o '"auth":"[^"]*"' | sort -u

# Search for any API key (alphanumeric strings near auth/key/token/secret)
unzip -p app.apk assets/index.android.bundle | strings | grep -oE '"(auth|key|token|secret)":"[^"]+"' | sort -u
```

Use `scripts/extract_token.sh` to run all three searches at once.

---

## Troubleshooting

### `libhermes.so not found` (React Native + Hermes)

The app has ARMv7 native libs but the emulator is ARM64-only.

**Fix:** Extract the libs from the armeabi-v7a split and push them manually:

```bash
# Extract libs from the split
unzip -o config.armeabi_v7a.apk -d arm_libs

# Find the installed app directory
adb shell "find /data/app -path '*com.package.app*' -type d" | head -3

# Create lib dir and copy
APP_DIR="/data/app/~~XXXX==/com.package.app-YYYY=="
adb shell "mkdir -p ${APP_DIR}/lib/arm"
adb push arm_libs/lib/armeabi-v7a/. ${APP_DIR}/lib/arm/
```

### `frida-ps: command not found`

```bash
export PATH="$PATH:/Library/Frameworks/Python.framework/Versions/3.12/bin"
```

### `--no-pause` flag not recognized

Remove the flag. In Frida 17+ it no longer exists; the app starts automatically.

### `--codeshare` fails with SSL error

Do not use `--codeshare`. Use the local script with `-l scripts/jp_intercept.js`.

### Emulator not detected by frida-ps

The emulator lost the adb connection. Restart:
```bash
adb kill-server && adb start-server
adb root
adb shell "nohup /data/local/tmp/frida-server > /dev/null 2>&1 &"
```

### RealCall class not found

The app may use a different OkHttp version. Try alternative paths in `jp_intercept.js`:
```javascript
var RealCall = Java.use('okhttp3.internal.call.RealCall');  // older versions
// or
var RealCall = Java.use('okhttp3.RealCall');                // some versions
```

---

## Files in this session

| File | Description |
|------|-------------|
| `scripts/jp_intercept.js` | Frida script: SSL bypass + full HTTP interceptor |
| `scripts/extract_token.sh` | Extracts auth token from JS bundle without Frida |
| `.claude/plans/teams_analyzer_rewrite.md` | Full reimplementation plan with the discovered API |

---

## References

- [Frida docs](https://frida.re/docs/home/)
- [OkHttp3 internals](https://square.github.io/okhttp/)
- APK sources: [APKPure](https://apkpure.com) / [Uptodown](https://uptodown.com)
