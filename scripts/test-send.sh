#!/usr/bin/env bash
# Usage: scripts/test-send.sh you@busseinc.com
set -euo pipefail
TO="${1:?recipient required}"
echo "Relay test from $(hostname) at $(date)" | mail -s "Mail relay test $(hostname)" "$TO"
sleep 3
tail -n 20 /var/log/mail.log 2>/dev/null || journalctl -u postfix -n 20 --no-pager
