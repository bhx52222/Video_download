#!/bin/bash
# Explicit installer; does not change network settings or browser sessions.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
command -v uv >/dev/null || { echo '先安装 uv：brew install uv'; exit 1; }
command -v ffmpeg >/dev/null || { echo '先安装 FFmpeg：brew install ffmpeg'; exit 1; }
VENV="$HOME/.vx/venv"
uv python install 3.12
if [ ! -x "$VENV/bin/python" ]; then uv venv --python 3.12 "$VENV"; fi
uv pip install --python "$VENV/bin/python" -r "$ROOT/requirements.txt"
uv tool install yt-dlp --with yt-dlp-ejs
mkdir -p "$HOME/.vx/bin"
xcrun swiftc -O "$ROOT/scripts/src/visionocr.swift" -framework Vision -framework AppKit -o "$HOME/.vx/bin/visionocr"
if [ "${1:-}" = --asr ]; then
  uv pip install --python "$VENV/bin/python" -r "$ROOT/requirements-asr.txt"
fi
echo '运行环境已安装。转写模型在首次使用时下载。未修改代理、证书或登录态。'
