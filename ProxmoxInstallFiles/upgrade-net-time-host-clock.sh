#!/usr/bin/env bash
# Retrofit Offline Sync support onto an existing Net Time install (CT + host agent).
#
# Run on the Proxmox HOST after SCPing these files to /root/:
#   host_clock_agent.py  chrony_ops.py  main.py  models.py
#   upgrade-net-time-host-clock.sh
#
# Optional env:
#   CTID=105  NET_TIME_API_TOKEN=…  HOST_IP=10.10.50.205
#   NET_TIME_HOST_CLOCK_PORT=8721  NET_TIME_PORT=8720  BRIDGE=vmbr0

set -euo pipefail

CTID="${CTID:-105}"
NET_TIME_HOST_CLOCK_PORT="${NET_TIME_HOST_CLOCK_PORT:-8721}"
NET_TIME_PORT="${NET_TIME_PORT:-8720}"
HOST_IP="${HOST_IP:-}"
BRIDGE="${BRIDGE:-vmbr0}"

say() { printf '\n==> %s\n' "$*" >&2; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

command -v pct >/dev/null 2>&1 || die "Run on the Proxmox host"

if [[ -z "$HOST_IP" ]]; then
  HOST_IP="$(ip -4 -o addr show dev "$BRIDGE" 2>/dev/null | awk '{print $4}' | head -1 | cut -d/ -f1 || true)"
fi
if [[ -z "$HOST_IP" ]]; then
  HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
fi
[[ -n "$HOST_IP" ]] || die "Set HOST_IP= to the Proxmox address the CT can reach"

if [[ -z "${NET_TIME_API_TOKEN:-}" ]]; then
  NET_TIME_API_TOKEN="$(pct exec "$CTID" -- bash -lc 'grep ^NET_TIME_API_TOKEN= /etc/net-time.env 2>/dev/null | cut -d= -f2-' | tr -d '\r' || true)"
fi
[[ -n "${NET_TIME_API_TOKEN:-}" ]] || die "Set NET_TIME_API_TOKEN= (same as Core Configurator)"

[[ -f /root/host_clock_agent.py ]] || die "Missing /root/host_clock_agent.py"
[[ -f /root/chrony_ops.py ]] || die "Missing /root/chrony_ops.py"
[[ -f /root/main.py ]] || die "Missing /root/main.py"
[[ -f /root/models.py ]] || die "Missing /root/models.py"

say "Installing host clock agent on ${HOST_IP}:${NET_TIME_HOST_CLOCK_PORT}"
install -m 0755 /root/host_clock_agent.py /usr/local/sbin/net-time-host-clock
umask 077
cat > /etc/net-time-host-clock.env <<EOF
NET_TIME_API_TOKEN=${NET_TIME_API_TOKEN}
NET_TIME_HOST_CLOCK_PORT=${NET_TIME_HOST_CLOCK_PORT}
EOF
cat > /etc/systemd/system/net-time-host-clock.service <<'UNIT'
[Unit]
Description=Net Time host clock agent (Offline Sync for LXC)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=-/etc/net-time-host-clock.env
ExecStart=/usr/bin/python3 /usr/local/sbin/net-time-host-clock
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now net-time-host-clock
systemctl restart net-time-host-clock

say "Pushing updated Net Time API into CT $CTID"
pct push "$CTID" /root/chrony_ops.py /opt/net_time/chrony_ops.py
pct push "$CTID" /root/main.py /opt/net_time/main.py
pct push "$CTID" /root/models.py /opt/net_time/models.py

say "Pointing CT at host clock agent"
pct exec "$CTID" -- bash -lc "umask 077; cat > /etc/net-time.env <<EOF
NET_TIME_API_TOKEN=${NET_TIME_API_TOKEN}
NET_TIME_HOST_CLOCK_URL=http://${HOST_IP}:${NET_TIME_HOST_CLOCK_PORT}
NET_TIME_HOST_CLOCK_PORT=${NET_TIME_HOST_CLOCK_PORT}
EOF
systemctl restart net-time"

say "Health checks"
curl -fsS "http://127.0.0.1:${NET_TIME_HOST_CLOCK_PORT}/health" >/dev/null
pct exec "$CTID" -- curl -fsS "http://127.0.0.1:${NET_TIME_PORT}/health" >/dev/null
pct exec "$CTID" -- grep -n CAP_SYS_TIME /opt/net_time/chrony_ops.py | head -2

cat <<EOF

Done. Offline Sync should work via the Proxmox host agent.

  Host agent: http://${HOST_IP}:${NET_TIME_HOST_CLOCK_PORT}/health
  Also redeploy HA: core_configurator www panel for Attempt Online Sync / Offline Sync UI.

EOF
