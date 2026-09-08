#!/bin/bash
set -euo pipefail
SRC="$(cd "$(dirname "$0")/src/vendor/wxdecrypt" && pwd)"
command -v go >/dev/null || { echo '需要 Go：brew install go'; exit 1; }
mkdir -p "$HOME/.vx/bin"
go build -o "$HOME/.vx/bin/vx-wx-decrypt" "$SRC/main.go" "$SRC/decrypt.go"
