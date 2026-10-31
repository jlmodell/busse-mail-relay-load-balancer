# Busse Mail Relay

Outbound-only SMTP relay so ERP mail (invoices, documents) never fails during NAS maintenance or SMTP2GO hiccups.

```
Before:  ERP ──► Synology MailPlus (NAS1) ──► SMTP2GO
After:   ERP ──► Postfix relay (Proxmox LXC, queues to disk) ──► SMTP2GO
                 (optional 2nd node + keepalived VIP)
```

**Why not a load balancer in front of the NAS boxes?** A load balancer has no queue. If both backends are down the ERP's send fails. Postfix accepts the message, writes it to disk, and retries upstream for up to 5 days. The NAS boxes leave the mail path entirely.

## What doesn't change
- SMTP2GO is still the sending host, so recipient-side SPF/DKIM behavior is unchanged.
- Nothing inbound from the internet. The relay only accepts mail from the ERP IP.

## Setup (Debian 12 LXC)
1. Create an unprivileged Debian 12 LXC (1 vCPU, 512 MB RAM, 8 GB disk is plenty) with a static IP.
2. In SMTP2GO, create a dedicated SMTP user for this relay.
3. Clone the repo and run `sudo ./scripts/install.sh` (add `--keepalived` for the 2-node setup).
4. Edit `/etc/postfix/main.cf` placeholders (`<ERP_IP>`, `<RELAY_FQDN>`, `<YOUR_DOMAIN>`).
5. Edit `/etc/postfix/sasl_passwd`, then `postmap /etc/postfix/sasl_passwd && systemctl restart postfix`.
6. `./scripts/test-send.sh you@busseinc.com` and confirm `status=sent` in the log and in the SMTP2GO activity view.
7. Point the ERP's SMTP host at the relay IP (or the VIP), port 25.
8. Leave MailPlus running for a week as rollback, then retire it from the ERP path.

## Optional: two nodes
Build a second identical LXC, ideally on a different Proxmox host, and use `keepalived/keepalived-node2.conf`. The VIP moves if Postfix stops on the active node.

Caveat: each node queues on its own disk. If a node dies with mail in its queue, that mail goes out once the node comes back, not from the other node. For ERP volume this is usually fine.

## Operations
| Task | Command |
|---|---|
| Queue status | `./scripts/queue-status.sh` or `postqueue -p` |
| Retry queue now | `postqueue -f` |
| Logs | `tail -f /var/log/mail.log` or `journalctl -u postfix -f` |
| Delete one stuck message | `postsuper -d <QUEUE_ID>` |
| Maintenance on node 1 | `systemctl stop postfix` (VIP fails over), then do the work and start it again |

## Verify before production
- SMTP2GO host/port (`mail.smtp2go.com:587` assumed) and their message size limit.
- That the ERP doesn't need STARTTLS. The listener is plaintext, LAN-only, by design.
- `virtual_router_id` doesn't collide with other VRRP on the VLAN (UniFi gateways can use VRRP).
