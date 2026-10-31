#!/usr/bin/env bash
# Queue health. Non-zero exit if >= THRESHOLD messages stuck (for monitoring).
THRESHOLD="${1:-25}"
COUNT=$(docker exec busse-mail-relay postqueue -j 2>/dev/null | wc -l)
echo "Messages in queue: $COUNT"
docker exec busse-mail-relay postqueue -p | tail -n 5
[[ "$COUNT" -lt "$THRESHOLD" ]]
