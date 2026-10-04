#!/usr/bin/env bash
# Create a new, pinned runtime. Existing directories are never modified.
set -euo pipefail
COMFY_TARGET="${1:-/root/ComfyUI}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
COMFY_COMMIT="651ca296a73cd21c12a57eb8741d52e40dc6528f"
if [[ -e "$COMFY_TARGET" ]]; then
  echo "目标已存在：$COMFY_TARGET。现有环境请直接使用 install.py。" >&2
  exit 1
fi
"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 10), "Python >= 3.10 required"'
git clone https://github.com/Comfy-Org/ComfyUI.git "$COMFY_TARGET"
git -C "$COMFY_TARGET" checkout --detach "$COMFY_COMMIT"
"$PYTHON_BIN" -m venv --system-site-packages "$COMFY_TARGET/.venv"
"$COMFY_TARGET/.venv/bin/python" -m pip install -r "$COMFY_TARGET/requirements.txt"
echo "环境创建完成：$COMFY_TARGET。未下载模型、未安装绘作台、未启动服务。"
