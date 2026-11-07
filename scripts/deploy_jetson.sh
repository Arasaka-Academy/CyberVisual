#!/bin/bash
set -euo pipefail

case "${1:-}" in
  publish|status|rollback) ;;
  *) printf '%s\n' 'Usage: cybervisual-deploy {publish SHA SHA256|status [JOB_OR_SHA]|rollback [SHA]}' >&2; exit 64 ;;
esac

exec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LC_ALL=C.UTF-8 \
  /usr/bin/python3 -I /usr/local/lib/cybervisual-deploy/jetson_deploy.py "$@"
