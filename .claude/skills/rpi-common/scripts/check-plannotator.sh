set -euo pipefail

if ! command -v plannotator >/dev/null 2>&1; then
  echo "ERROR: plannotator is not installed."
  echo "Install it with: curl -fsSL https://plannotator.ai/install.sh | bash"
  exit 1
fi

echo "plannotator found at: $(command -v plannotator)"
