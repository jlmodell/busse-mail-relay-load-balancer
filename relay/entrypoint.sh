#!/bin/sh
# Configures Postfix from env vars, then runs it in the foreground (logs to stdout).
set -eu
: "${RELAY_HOSTNAME:?set RELAY_HOSTNAME}"
: "${RELAY_DOMAIN:?set RELAY_DOMAIN}"
: "${ALLOWED_NETWORKS:?set ALLOWED_NETWORKS}"
: "${SMTP2GO_USER:?set SMTP2GO_USER}"
: "${SMTP2GO_PASS:?set SMTP2GO_PASS}"
UPSTREAM="${UPSTREAM:-[mail.smtp2go.com]:587}"

postconf -e \
  "compatibility_level=3.6" \
  "myhostname=${RELAY_HOSTNAME}" \
  "mydomain=${RELAY_DOMAIN}" \
  'myorigin=$mydomain' \
  "mydestination=" \
  "local_recipient_maps=" \
  "local_transport=error:local delivery is disabled" \
  "alias_maps=" "alias_database=" \
  "inet_interfaces=all" "inet_protocols=ipv4" \
  "mynetworks=127.0.0.0/8 ${ALLOWED_NETWORKS}" \
  "smtpd_relay_restrictions=permit_mynetworks, reject_unauth_destination" \
  "smtpd_recipient_restrictions=permit_mynetworks, reject" \
  "smtpd_client_restrictions=permit_mynetworks, reject" \
  "smtpd_tls_security_level=none" \
  "smtpd_sasl_auth_enable=no" \
  "relayhost=${UPSTREAM}" \
  "smtp_sasl_auth_enable=yes" \
  "smtp_sasl_password_maps=hash:/etc/postfix/sasl_passwd" \
  "smtp_sasl_security_options=noanonymous" \
  "smtp_sasl_tls_security_options=noanonymous" \
  "smtp_tls_security_level=encrypt" \
  "smtp_tls_CAfile=/etc/ssl/certs/ca-certificates.crt" \
  "smtp_tls_loglevel=1" \
  "maximal_queue_lifetime=${QUEUE_LIFETIME:-5d}" \
  "bounce_queue_lifetime=${QUEUE_LIFETIME:-5d}" \
  "queue_run_delay=300s" "minimal_backoff_time=300s" "maximal_backoff_time=1800s" \
  "message_size_limit=${MESSAGE_SIZE_LIMIT:-52428800}" \
  "mailbox_size_limit=0" \
  "disable_vrfy_command=yes" \
  "local_header_rewrite_clients=permit_mynetworks" \
  'smtpd_banner=$myhostname ESMTP' \
  "maillog_file=/var/log/postfix/mail.log" \
  "header_checks=regexp:/etc/postfix/header_checks"

[ -n "${BOUNCE_NOTICE_TO:-}" ] && postconf -e "notify_classes=bounce, resource, software" "bounce_notice_recipient=${BOUNCE_NOTICE_TO}"

printf '%s %s:%s\n' "$UPSTREAM" "$SMTP2GO_USER" "$SMTP2GO_PASS" > /etc/postfix/sasl_passwd
chmod 600 /etc/postfix/sasl_passwd
postmap hash:/etc/postfix/sasl_passwd

# Postfix runs chrooted services; give them DNS + CA certs
mkdir -p /var/spool/postfix/etc
cp /etc/resolv.conf /etc/services /etc/hosts /var/spool/postfix/etc/ 2>/dev/null || true

# Log each message's Subject so the watcher can include it
printf '/^Subject:/ WARN\n' > /etc/postfix/header_checks

# File log on the host (./logs) + mirror to stdout for docker logs
mkdir -p /var/log/postfix && touch /var/log/postfix/mail.log
tail -n0 -F /var/log/postfix/mail.log &

postfix set-permissions >/dev/null 2>&1 || true
postfix check
exec postfix start-fg
