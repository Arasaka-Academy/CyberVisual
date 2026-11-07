#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec /usr/bin/python3 -I -B "$ROOT_DIR/scripts/jetson_bootstrap.py" "$@"
