#!/usr/bin/env bash
# Quick queue health check. Non-zero exit if mail is stuck (for monitoring).
COUNT=$(postqueue -j 2>/dev/null | wc -l)
echo "Messages in queue: $COUNT"
postqueue -p | tail -n 5
[[ "$COUNT" -lt 25 ]]
