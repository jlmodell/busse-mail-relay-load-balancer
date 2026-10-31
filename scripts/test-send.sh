#!/usr/bin/env bash
# Usage: scripts/test-send.sh you@busseinc.com [relay-ip]
# Sends a test message over SMTP like the ERP would (needs swaks: apt install swaks)
set -euo pipefail
TO="${1:?recipient required}"; RELAY="${2:-127.0.0.1}"
swaks --server "$RELAY" --port 25 --to "$TO" --from "erp-test@${RELAY_DOMAIN:-busseinc.com}" \
      --header "Subject: Mail relay test $(hostname) $(date +%F_%T)"
docker logs --tail 20 busse-mail-relay
