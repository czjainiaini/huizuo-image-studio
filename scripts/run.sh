#!/usr/bin/env bash
set -euo pipefail
COMFY_TARGET="${1:-/root/ComfyUI}"
SERVICE_PORT="${2:-6006}"
[[ "$SERVICE_PORT" =~ ^[0-9]+$ ]] && (( SERVICE_PORT >= 1 && SERVICE_PORT <= 65535 )) || { echo "端口无效" >&2; exit 1; }
if [[ -x "$COMFY_TARGET/.venv/bin/python" ]]; then
  COMFY_PYTHON="$COMFY_TARGET/.venv/bin/python"
else
  COMFY_PYTHON="${PYTHON_BIN:-python3}"
fi
cd -- "$COMFY_TARGET"
exec "$COMFY_PYTHON" main.py --listen 0.0.0.0 --port "$SERVICE_PORT" --lowvram
