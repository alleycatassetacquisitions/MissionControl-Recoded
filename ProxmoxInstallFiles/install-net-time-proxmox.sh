#!/usr/bin/env bash
# Create a Net Time LXC on this Proxmox node.
#
# Net Time is the Mission Control LAN NTP authority (chrony + management API).
# The CT is privileged so Sync Now / chrony can set the system clock.
#
# Run on the Proxmox HOST shell (the node, not a guest). Matches
# Docs/Net Time Config Steps.md
#
# Phone walkthrough: open the node Shell in the Proxmox UI, paste:
#   bash install-net-time-proxmox.sh
#
# Optional environment overrides:
#   CTID=130 STORAGE=local-lvm TEMPLATE_STORAGE=local BRIDGE=vmbr0
#   CORES=1 MEMORY_MB=512 DISK_SIZE=4 START_CT=1
#   NET_TIME_PORT=8720  NET_TIME_API_TOKEN=...  NET_TIME_SRC=/path/to/Server_Component
#   REPO_URL=https://github.com/alleycatassetacquisitions/MissionControl-Recoded.git
#   ROOT_PASSWORD=alleycat  (console / SSH root password for all Mission Control LXCs)
#   TEMPLATE=ubuntu-24.04-standard  SKIP_CONFIRM=0
# CTID is optional. If omitted (or already in use), the next free ID is used.

set -euo pipefail

REQUESTED_CTID="${CTID:-}"
CT_NAME="${CT_NAME:-Net-Time}"
HOSTNAME="${HOSTNAME_NET_TIME:-net-time}"
STORAGE="${STORAGE:-local-lvm}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
BRIDGE="${BRIDGE:-vmbr0}"
CORES="${CORES:-1}"
MEMORY_MB="${MEMORY_MB:-512}"
DISK_SIZE="${DISK_SIZE:-4}"
START_CT="${START_CT:-1}"
NET_TIME_PORT="${NET_TIME_PORT:-8720}"
TEMPLATE_PREFIX="${TEMPLATE:-ubuntu-24.04-standard}"
NET_TIME_API_TOKEN="${NET_TIME_API_TOKEN:-}"
NET_TIME_SRC="${NET_TIME_SRC:-}"
REPO_URL="${REPO_URL:-https://github.com/alleycatassetacquisitions/MissionControl-Recoded.git}"
ROOT_PASSWORD="${ROOT_PASSWORD:-alleycat}"
SKIP_CONFIRM="${SKIP_CONFIRM:-0}"

say() { printf '\n==> %s\n' "$*" >&2; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

require_proxmox() {
  command -v pct >/dev/null 2>&1 || die "pct not found. Run this on the Proxmox node shell, not inside a guest."
  command -v pveam >/dev/null 2>&1 || die "pveam not found. This does not look like a Proxmox host."
  command -v pvesm >/dev/null 2>&1 || die "pvesm not found. This does not look like a Proxmox host."
}

ctid_in_use() {
  # Cluster IDs are shared by LXCs and QEMU VMs — check both.
  pct status "$1" >/dev/null 2>&1 && return 0
  if command -v qm >/dev/null 2>&1; then
    qm status "$1" >/dev/null 2>&1 && return 0
  fi
  return 1
}

next_free_ctid() {
  local id="$1"
  while ctid_in_use "$id"; do
    id=$((id + 1))
    if [[ "$id" -gt 999999999 ]]; then
      die "Could not find a free CT ID."
    fi
  done
  printf '%s' "$id"
}

cluster_next_id() {
  local id=""
  if command -v pvesh >/dev/null 2>&1; then
    id="$(pvesh get /cluster/nextid 2>/dev/null | tr -d '[:space:]' || true)"
  fi
  if [[ "$id" =~ ^[0-9]+$ ]] && ! ctid_in_use "$id"; then
    printf '%s' "$id"
    return 0
  fi
  next_free_ctid 100
}

choose_ctid() {
  if [[ -n "$REQUESTED_CTID" ]]; then
    if ctid_in_use "$REQUESTED_CTID"; then
      printf '\n==> CTID %s is already in use; choosing the next free ID\n' "$REQUESTED_CTID" >&2
    else
      printf '%s' "$REQUESTED_CTID"
      return 0
    fi
  fi
  cluster_next_id
}

storage_exists() {
  pvesm status --storage "$1" >/dev/null 2>&1
}

generate_token() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  else
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

resolve_template() {
  local listed match filename
  say "Looking for template matching '${TEMPLATE_PREFIX}' on ${TEMPLATE_STORAGE}"
  listed="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null | awk 'NR>1 {print $1}' || true)"
  match="$(printf '%s\n' "$listed" | grep -F "${TEMPLATE_PREFIX}" | head -1 || true)"
  if [[ -n "$match" ]]; then
    printf '%s' "$match"
    return 0
  fi

  say "Template not cached — updating appliance list and downloading"
  pveam update >/dev/null || true

  match="$(pveam available 2>/dev/null | awk '{print $2}' | grep -F "${TEMPLATE_PREFIX}" | head -1 || true)"
  if [[ -z "$match" ]]; then
    match="$(pveam available --section system 2>/dev/null | awk '{print $2}' | grep -F "${TEMPLATE_PREFIX}" | head -1 || true)"
  fi
  if [[ -z "$match" ]]; then
    printf '\nAvailable templates (first 30):\n' >&2
    pveam available 2>/dev/null | head -30 >&2 || true
    die "Could not find a template matching '${TEMPLATE_PREFIX}'. Set TEMPLATE= and retry."
  fi

  say "Downloading $match to ${TEMPLATE_STORAGE}"
  filename="$match"
  pveam download "$TEMPLATE_STORAGE" "$filename"

  listed="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null | awk 'NR>1 {print $1}' || true)"
  match="$(printf '%s\n' "$listed" | grep -F "${TEMPLATE_PREFIX}" | head -1 || true)"
  if [[ -n "$match" ]]; then
    printf '%s' "$match"
    return 0
  fi

  printf '%s:vztmpl/%s' "$TEMPLATE_STORAGE" "$filename"
}

wait_for_network() {
  local i ip
  for i in $(seq 1 30); do
    ip="$(pct exec "$CTID" -- bash -c "hostname -I 2>/dev/null | awk '{print \$1}'" 2>/dev/null | tr -d '[:space:]' || true)"
    if [[ -n "$ip" ]]; then
      printf '%s' "$ip"
      return 0
    fi
    sleep 2
  done
  return 1
}

install_net_time_into_ct() {
  say "Installing chrony, Python, and Net Time inside CT $CTID"
  pct exec "$CTID" -- bash -lc '
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq chrony python3 python3-pip python3-venv ca-certificates curl
    mkdir -p /opt/net_time
  '

  if [[ -n "$NET_TIME_SRC" ]]; then
    [[ -d "$NET_TIME_SRC" ]] || die "NET_TIME_SRC is not a directory: $NET_TIME_SRC"
    say "Copying Net Time from $NET_TIME_SRC"
    tar -C "$NET_TIME_SRC" -cf - . | pct exec "$CTID" -- tar -C /opt/net_time -xf -
  else
    say "Cloning Net Time from $REPO_URL"
    pct exec "$CTID" -- bash -lc "
      set -euo pipefail
      export DEBIAN_FRONTEND=noninteractive
      apt-get install -y -qq git
      rm -rf /tmp/mc-src
      git clone --depth 1 '$REPO_URL' /tmp/mc-src
      cp -a /tmp/mc-src/Apps/Net_Time/Server_Component/. /opt/net_time/
      rm -rf /tmp/mc-src
    "
  fi

  pct exec "$CTID" -- bash -lc '
    set -euo pipefail
    if [[ -f /opt/net_time/chrony.conf ]]; then
      cp /opt/net_time/chrony.conf /etc/chrony/chrony.conf
    fi
    systemctl enable chrony
    systemctl restart chrony
  '

  pct exec "$CTID" -- bash -lc '
    set -euo pipefail
    cd /opt/net_time
    python3 -m venv /opt/net_time/.venv
    /opt/net_time/.venv/bin/pip install -q --upgrade pip
    if [[ -f pyproject.toml ]]; then
      /opt/net_time/.venv/bin/pip install -q .
    else
      /opt/net_time/.venv/bin/pip install -q fastapi "uvicorn[standard]" pydantic
    fi
  '

  # Host expands ${NET_TIME_PORT}; guest heredoc is quoted so nothing else expands.
  pct exec "$CTID" -- bash -lc "cat > /etc/systemd/system/net-time.service <<'UNIT'
[Unit]
Description=Net Time management API
After=network-online.target chrony.service
Wants=network-online.target
Requires=chrony.service

[Service]
Type=simple
WorkingDirectory=/opt/net_time
EnvironmentFile=-/etc/net-time.env
ExecStart=/opt/net_time/.venv/bin/uvicorn main:app --host 0.0.0.0 --port ${NET_TIME_PORT}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT"

  pct exec "$CTID" -- bash -lc "
    set -euo pipefail
    umask 077
    cat > /etc/net-time.env <<EOF
NET_TIME_API_TOKEN=${NET_TIME_API_TOKEN}
EOF
    systemctl daemon-reload
    systemctl enable net-time
    systemctl restart net-time
  "
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

require_proxmox
storage_exists "$STORAGE" || die "Storage '$STORAGE' was not found. Check Datacenter → Storage."
storage_exists "$TEMPLATE_STORAGE" || die "Template storage '$TEMPLATE_STORAGE' was not found."

CTID="$(choose_ctid)"
TEMPLATE_REF="$(resolve_template | tr -d '\r')"
if [[ -z "$TEMPLATE_REF" || "$TEMPLATE_REF" == *$'\n'* || "${#TEMPLATE_REF}" -gt 255 ]]; then
  die "Bad ostemplate from resolve_template (len=${#TEMPLATE_REF}): ${TEMPLATE_REF:0:120}"
fi

if [[ -z "$NET_TIME_API_TOKEN" ]]; then
  NET_TIME_API_TOKEN="$(generate_token)"
fi

cat <<EOF

This will create a Net Time LXC on this Proxmox node:

  CTID            $CTID
  Name            $CT_NAME
  Hostname        $HOSTNAME
  Template        $TEMPLATE_REF
  Privileged      yes (required to set system clock)
  CPU             ${CORES} cores
  Memory          ${MEMORY_MB} MiB
  Disk            ${DISK_SIZE}G on ${STORAGE}
  Bridge          ${BRIDGE}
  API port        ${NET_TIME_PORT}
  NTP             UDP 123
  Root password   ${ROOT_PASSWORD}
  Start after     $([[ "$START_CT" == "1" ]] && echo yes || echo no)
  Source          $([[ -n "$NET_TIME_SRC" ]] && echo "$NET_TIME_SRC" || echo "git $REPO_URL")

EOF

if [[ "$SKIP_CONFIRM" != "1" ]]; then
  say "Starting in 5 seconds. Press Ctrl-C to cancel."
  sleep 5
fi

say "Creating CT $CTID ($CT_NAME) — privileged for clock control"
pct create "$CTID" "$TEMPLATE_REF" \
  --hostname "$HOSTNAME" \
  --memory "$MEMORY_MB" \
  --cores "$CORES" \
  --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp" \
  --storage "$STORAGE" \
  --rootfs "${STORAGE}:${DISK_SIZE}" \
  --unprivileged 0 \
  --features nesting=1 \
  --onboot 1 \
  --ostype ubuntu \
  --password "$ROOT_PASSWORD" \
  --description "Mission Control — Net Time (LAN NTP authority)"

pct set "$CTID" --hostname "$HOSTNAME" >/dev/null

# Sync Now needs CAP_SYS_TIME. Proxmox forbids mixing lxc.cap.keep with lxc.cap.drop —
# so if sys_time is in a drop list, remove it from that list (never add cap.keep).
CT_CONF="/etc/pve/lxc/${CTID}.conf"
if [[ -f "$CT_CONF" ]]; then
  if grep -qE '^lxc\.cap\.drop:' "$CT_CONF"; then
    say "Ensuring sys_time is not in lxc.cap.drop (required for Sync Now)"
    # Drop "sys_time" token from the drop list; leave other drops intact.
    sed -i -E 's/^(lxc\.cap\.drop:.*)(\s|^)sys_time(\s|$)/\1\3/g; s/  +/ /g; s/: /: /' "$CT_CONF" || true
  fi
  # Clean up any mistaken keep lines from older install attempts.
  sed -i -E '/^lxc\.cap\.keep:.*sys_time/d' "$CT_CONF" || true
fi

say "Starting CT $CTID"
pct start "$CTID"
sleep 2
echo "root:${ROOT_PASSWORD}" | pct exec "$CTID" -- chpasswd

say "Waiting for network"
CT_IP="$(wait_for_network)" || die "CT started but no IP yet. Check DHCP on ${BRIDGE}, then: pct enter ${CTID}"

install_net_time_into_ct

say "Checking /health"
if pct exec "$CTID" -- curl -fsS "http://127.0.0.1:${NET_TIME_PORT}/health" >/dev/null; then
  say "Net Time health check OK"
else
  say "Health check not ready yet — give it a few seconds and curl from your PC"
fi

say "chronyc tracking (best effort)"
pct exec "$CTID" -- chronyc tracking >/dev/null 2>&1 || true

cat <<EOF

Done. CT $CTID ($CT_NAME) is ready.

Console / SSH login:
  user: root
  password: ${ROOT_PASSWORD}
  (or from the Proxmox host: pct enter ${CTID})

Put these values into Home Assistant Core Configurator / secrets.yaml:

  cc_net_time:       http://${CT_IP}:${NET_TIME_PORT}
  cc_net_time_token: ${NET_TIME_API_TOKEN}

Quick checks:
  curl http://${CT_IP}:${NET_TIME_PORT}/health
  curl -H "Authorization: Bearer ${NET_TIME_API_TOKEN}" http://${CT_IP}:${NET_TIME_PORT}/status
  pct enter ${CTID}
  systemctl status net-time chrony
  chronyc tracking
  chronyc sources

NTP clients (FDN / PDN team): point SNTP at ${CT_IP} (UDP 123).

Next: Docs/Net Time Config Steps.md (paste into HA, Confirm online / Sync Now).

EOF
