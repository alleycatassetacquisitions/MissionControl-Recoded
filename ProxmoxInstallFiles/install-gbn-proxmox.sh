#!/usr/bin/env bash
# Create a Galactic Bounty Network LXC on this Proxmox node.
#
# Run on the Proxmox HOST shell. Matches Docs/GBN Config Steps.md
#
# Optional environment overrides:
#   CTID= STORAGE=local-lvm TEMPLATE_STORAGE=local BRIDGE=vmbr0
#   CORES=1 MEMORY_MB=1024 DISK_SIZE=8 START_CT=1
#   GBN_SRC=/path/to/Server_Component
#   GBN_PUBLIC_BASE=http://<ip>:8100
#   GBN_MCS_BASE=http://<mcs-ip>:8700  GBN_MCS_TOKEN=...
#   REPO_URL=https://github.com/alleycatassetacquisitions/MissionControl-Recoded.git
#   ROOT_PASSWORD=alleycat  TEMPLATE=ubuntu-24.04-standard  SKIP_CONFIRM=0

set -euo pipefail

REQUESTED_CTID="${CTID:-}"
CT_NAME="${CT_NAME:-Galactic-Bounty-Network}"
HOSTNAME="${HOSTNAME_GBN:-gbn}"
STORAGE="${STORAGE:-local-lvm}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
BRIDGE="${BRIDGE:-vmbr0}"
CORES="${CORES:-1}"
MEMORY_MB="${MEMORY_MB:-1024}"
DISK_SIZE="${DISK_SIZE:-8}"
START_CT="${START_CT:-1}"
GBN_PORT="${GBN_PORT:-8100}"
TEMPLATE_PREFIX="${TEMPLATE:-ubuntu-24.04-standard}"
GBN_SRC="${GBN_SRC:-}"
GBN_PUBLIC_BASE="${GBN_PUBLIC_BASE:-}"
GBN_MCS_BASE="${GBN_MCS_BASE:-}"
GBN_MCS_TOKEN="${GBN_MCS_TOKEN:-}"
REPO_URL="${REPO_URL:-https://github.com/alleycatassetacquisitions/MissionControl-Recoded.git}"
ROOT_PASSWORD="${ROOT_PASSWORD:-alleycat}"
SKIP_CONFIRM="${SKIP_CONFIRM:-0}"

say() { printf '\n==> %s\n' "$*" >&2; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

require_proxmox() {
  command -v pct >/dev/null 2>&1 || die "pct not found. Run on the Proxmox node shell."
  command -v pvesm >/dev/null 2>&1 || die "pvesm not found. This does not look like a Proxmox host."
}

# Busy if either an LXC or a QEMU VM already owns the ID.
ctid_in_use() {
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
    [[ "$id" -gt 999999999 ]] && die "Could not find a free CT ID."
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
      say "CTID $REQUESTED_CTID is already in use; choosing the next free ID"
    else
      printf '%s' "$REQUESTED_CTID"
      return 0
    fi
  fi
  cluster_next_id
}

resolve_template() {
  local listed match filename
  listed="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null | awk 'NR>1 {print $1}' || true)"
  match="$(printf '%s\n' "$listed" | grep -F "${TEMPLATE_PREFIX}" | head -1 || true)"
  if [[ -n "$match" ]]; then printf '%s' "$match"; return 0; fi
  pveam update >/dev/null || true
  match="$(pveam available 2>/dev/null | awk '{print $2}' | grep -F "${TEMPLATE_PREFIX}" | head -1 || true)"
  [[ -n "$match" ]] || die "Template '${TEMPLATE_PREFIX}' not found."
  pveam download "$TEMPLATE_STORAGE" "$match"
  listed="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null | awk 'NR>1 {print $1}' || true)"
  match="$(printf '%s\n' "$listed" | grep -F "${TEMPLATE_PREFIX}" | head -1 || true)"
  if [[ -n "$match" ]]; then printf '%s' "$match"; return 0; fi
  printf '%s:vztmpl/%s' "$TEMPLATE_STORAGE" "$match"
}

wait_for_network() {
  local i ip
  for i in $(seq 1 30); do
    ip="$(pct exec "$CTID" -- bash -c "hostname -I 2>/dev/null | awk '{print \$1}'" 2>/dev/null | tr -d '[:space:]' || true)"
    if [[ -n "$ip" ]]; then printf '%s' "$ip"; return 0; fi
    sleep 2
  done
  return 1
}

require_proxmox
CTID="$(choose_ctid)"

TEMPLATE_REF="$(resolve_template)"
say "Will create CT $CTID ($CT_NAME) from $TEMPLATE_REF"
if [[ "$SKIP_CONFIRM" != "1" ]]; then
  read -rp "Continue? [y/N]: " CONFIRM
  [[ "${CONFIRM,,}" == "y" ]] || die "Aborted."
fi

pct create "$CTID" "$TEMPLATE_REF" \
  --hostname "$HOSTNAME" \
  --cores "$CORES" \
  --memory "$MEMORY_MB" \
  --rootfs "${STORAGE}:${DISK_SIZE}" \
  --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp" \
  --unprivileged 1 \
  --features nesting=1 \
  --onboot 1 \
  --password "$ROOT_PASSWORD" \
  --start 0

[[ "$START_CT" == "1" ]] && pct start "$CTID"
IP="$(wait_for_network || true)"
[[ -n "$IP" ]] || die "CT has no IP yet — start it and re-run install inside the guest."

PUBLIC="${GBN_PUBLIC_BASE:-http://${IP}:${GBN_PORT}}"

say "Installing GBN into CT $CTID"
pct exec "$CTID" -- bash -lc '
  set -euo pipefail
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-pip python3-venv ca-certificates curl
  useradd --system --no-create-home --shell /usr/sbin/nologin gbn 2>/dev/null || true
  mkdir -p /opt/gbn
'

if [[ -n "$GBN_SRC" ]]; then
  [[ -d "$GBN_SRC" ]] || die "GBN_SRC is not a directory: $GBN_SRC"
  tar -C "$GBN_SRC" -cf - . | pct exec "$CTID" -- tar -C /opt/gbn -xf -
else
  pct exec "$CTID" -- bash -lc "
    set -euo pipefail
    apt-get install -y -qq git
    rm -rf /tmp/mc-src
    git clone --depth 1 '$REPO_URL' /tmp/mc-src
    cp -a /tmp/mc-src/Apps/Galactic_Bounty_Network/Server_Component/. /opt/gbn/
    rm -rf /tmp/mc-src
  "
fi

pct exec "$CTID" -- bash -lc "
  set -euo pipefail
  cd /opt/gbn
  python3 -m venv /opt/gbn/.venv
  /opt/gbn/.venv/bin/pip install -q --upgrade pip
  /opt/gbn/.venv/bin/pip install -q -r requirements.txt
  mkdir -p media/videos media/assets/neocorp media/assets/animations media/assets/marks data
  chown -R gbn:gbn /opt/gbn
  cat > /etc/gbn.env <<EOF
GBN_HOST=0.0.0.0
GBN_PORT=${GBN_PORT}
GBN_PUBLIC_BASE=${PUBLIC}
GBN_MEDIA=/opt/gbn/media
GBN_DATA=/opt/gbn/data
GBN_POSTERS=/opt/gbn/data/posters.json
GBN_MCS_BASE=${GBN_MCS_BASE}
GBN_MCS_TOKEN=${GBN_MCS_TOKEN}
EOF
  chmod 640 /etc/gbn.env
  chown root:gbn /etc/gbn.env
  cat > /etc/systemd/system/gbn.service <<UNIT
[Unit]
Description=Galactic Bounty Network poster server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=gbn
Group=gbn
WorkingDirectory=/opt/gbn
EnvironmentFile=-/etc/gbn.env
ExecStart=/opt/gbn/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${GBN_PORT}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now gbn
"

say "GBN ready"
echo "  CTID:   $CTID"
echo "  IP:     $IP"
echo "  Health: curl -s ${PUBLIC}/health"
echo "  Set Core Configurator key gbn to: ${PUBLIC}"
