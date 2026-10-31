#!/usr/bin/env bash
# Install Postfix relay on Debian 12 LXC/VM. Run as root from the repo root.
set -euo pipefail

echo "postfix postfix/main_mailer_type select No configuration" | debconf-set-selections
apt-get update
apt-get install -y postfix libsasl2-modules ca-certificates mailutils

cp postfix/main.cf /etc/postfix/main.cf
if grep -q '<' /etc/postfix/main.cf; then
  echo "!! main.cf still has <PLACEHOLDER> values - edit /etc/postfix/main.cf"
fi

if [[ ! -f /etc/postfix/sasl_passwd ]]; then
  cp postfix/sasl_passwd.example /etc/postfix/sasl_passwd
  echo "!! Edit /etc/postfix/sasl_passwd with SMTP2GO creds, then run:"
  echo "   postmap /etc/postfix/sasl_passwd && systemctl restart postfix"
fi
chmod 600 /etc/postfix/sasl_passwd

postmap /etc/postfix/sasl_passwd || true
postfix check
systemctl enable --now postfix
systemctl restart postfix

if [[ "${1:-}" == "--keepalived" ]]; then
  apt-get install -y keepalived
  echo "Copy keepalived/keepalived-node1.conf (or node2) to /etc/keepalived/keepalived.conf,"
  echo "fill placeholders, then: systemctl enable --now keepalived"
fi
echo "Done. Test with scripts/test-send.sh"
