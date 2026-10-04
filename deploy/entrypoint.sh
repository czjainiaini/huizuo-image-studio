#!/usr/bin/env bash
set -euo pipefail
COMFY_ROOT="${COMFY_ROOT:-/opt/ComfyUI}"
HUIZUO_PORT="${HUIZUO_PORT:-6006}"
HUIZUO_DEVICE="${HUIZUO_DEVICE:-cuda}"
[[ "$HUIZUO_PORT" =~ ^[0-9]+$ ]] && (( HUIZUO_PORT >= 1 && HUIZUO_PORT <= 65535 )) || { echo "端口无效" >&2; exit 1; }
cd -- "$COMFY_ROOT"
if [[ "$HUIZUO_DEVICE" != cpu && "$HUIZUO_DEVICE" != cuda ]]; then
    echo "HUIZUO_DEVICE 仅支持 cuda 或 cpu" >&2; exit 1
fi
exec python /opt/huizuo/scripts/docker_gateway_entry.py "$@"
