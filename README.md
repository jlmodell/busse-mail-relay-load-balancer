# Busse Mail Relay

Outbound-only SMTP relay in Docker so ERP mail (invoices, documents) never fails during NAS maintenance or SMTP2GO hiccups.

```
Before:  ERP ──► Synology MailPlus (NAS) ──► SMTP2GO
After:   ERP ──► Postfix container (queues to a volume) ──► SMTP2GO
                 (optional 2nd host + keepalived VIP)
```

**Why not a load balancer in front of the NAS boxes?** A load balancer has no queue. If the backends are down, the ERP's send fails. Postfix accepts the message, writes it to disk, and retries SMTP2GO for up to 5 days. The NAS boxes leave the mail path entirely.

## What doesn't change
- SMTP2GO is still the sending host, so recipient-side SPF/DKIM behavior is the same.
- Nothing inbound from the internet. Only `ALLOWED_NETWORKS` can relay.

## Setup
1. On a Docker host (Proxmox VM or LXC with Docker), clone this repo.
2. Create a dedicated SMTP user for this relay in SMTP2GO.
3. `cp .env.example .env` and fill it in.
4. `docker compose up -d --build`, then `docker logs -f busse-mail-relay`.
5. `./scripts/test-send.sh you@busseinc.com` and confirm `status=sent` in the logs and in SMTP2GO's activity view.
6. Point the ERP's SMTP host at the Docker host IP (or the VIP), port 25.
7. Leave MailPlus configured for a week as rollback, then retire it from the path.

### Notes
- **Host networking is deliberate.** With bridge networking and published ports, Docker can rewrite the client source IP in some setups (userland-proxy, hairpin), which would break the allowlist. `network_mode: host` avoids that. Nothing else on the host can use port 25.
- **The queue lives in the `spool` volume.** `docker compose down` keeps it; `down -v` deletes queued mail.

## Logs & Discord notifications
The `log-watcher` container tails Postfix's log and writes one line per message to the host:

| File | Contents |
|---|---|
| `./logs/sent.log` | Delivered to SMTP2GO (250 OK + SMTP2GO message id) |
| `./logs/rejected.log` | Allowlist rejections, bounces, and messages that expired in the queue |
| `./logs/deferred.log` | First temporary failure per message (it's still queued and retrying) |
| `./logs/mail.log` | Raw Postfix log |

Format: `timestamp | STATUS | from -> to | subject | client | qid | relay | detail`

Set `DISCORD_WEBHOOK_URL` in `.env` to get Discord embeds. `DISCORD_NOTIFY` picks which statuses post (default: everything except `sent`).

The logs grow without limit. For high volume, add a host logrotate rule with `copytruncate` on `./logs/*.log`; the watcher handles truncation.

## Security: the /21 allowlist
Anything on the LAN can send through this relay as your domain without auth, including a compromised PC. Mitigations:
- In SMTP2GO, restrict allowed sender addresses/domains for this SMTP user, and set a sending rate limit if your plan offers one.
- Optionally narrow `ALLOWED_NETWORKS` later to the server VLAN and the ERP, printer, and scanner IPs.
- Check the SMTP2GO activity view for unexpected senders.

## Optional: two hosts
Run the same compose stack on a second Docker host, ideally on a different Proxmox node. Install keepalived **on each host** with `keepalived/keepalived-node1.conf` / `node2.conf`. The VIP moves if the container stops. Each host queues on its own volume: if a host dies with mail queued, that mail goes out when the host returns.

## Operations
| Task | Command |
|---|---|
| Queue status | `./scripts/queue-status.sh` |
| List queue | `docker exec busse-mail-relay postqueue -p` |
| Retry now | `docker exec busse-mail-relay postqueue -f` |
| Logs | `docker logs -f busse-mail-relay` |
| Delete a message | `docker exec busse-mail-relay postsuper -d <QUEUE_ID>` |
| Rebuild/upgrade | `docker compose up -d --build` (queue preserved) |

## Verify before production
- SMTP2GO host/port (`mail.smtp2go.com:587` assumed) and their message size limit.
- The ERP sends plain SMTP on port 25 with no STARTTLS. The listener is plaintext, LAN-only, by design.
- `virtual_router_id` doesn't collide with other VRRP on the VLAN.
