#!/usr/bin/env bash
# Create a Master Control Server LXC on this Proxmox node.
#
# Run on the Proxmox HOST shell (the node, not a guest). Matches
# Docs/Master Control Server Config Steps.md
#
# Phone walkthrough: open the node Shell in the Proxmox UI, paste:
#   bash install-mcs-proxmox.sh
#
# Optional environment overrides:
#   CTID=120 STORAGE=local-lvm TEMPLATE_STORAGE=local BRIDGE=vmbr0
#   CORES=1 MEMORY_MB=1024 DISK_SIZE=8 START_CT=1
#   MCS_API_TOKEN=...  MCS_SRC=/path/to/Server_Component
#   REPO_URL=https://github.com/alleycatassetacquisitions/MissionContorl-Recoded.git
#   ROOT_PASSWORD=alleycat  (console / SSH root password for all Mission Control LXCs)
#   TEMPLATE=ubuntu-24.04-standard  SKIP_CONFIRM=0
# CTID is optional. If omitted (or already in use), the next free ID is used.

set -euo pipefail

REQUESTED_CTID="${CTID:-}"
CT_NAME="${CT_NAME:-Master-Control-Server}"
HOSTNAME="${HOSTNAME_MCS:-master-control-server}"
STORAGE="${STORAGE:-local-lvm}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
BRIDGE="${BRIDGE:-vmbr0}"
CORES="${CORES:-1}"
MEMORY_MB="${MEMORY_MB:-1024}"
DISK_SIZE="${DISK_SIZE:-8}"
START_CT="${START_CT:-1}"
MCS_PORT="${MCS_PORT:-8700}"
TEMPLATE_PREFIX="${TEMPLATE:-ubuntu-24.04-standard}"
MCS_API_TOKEN="${MCS_API_TOKEN:-}"
MCS_SRC="${MCS_SRC:-}"
REPO_URL="${REPO_URL:-https://github.com/alleycatassetacquisitions/MissionContorl-Recoded.git}"
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
    # pveam list prints storage:vztmpl/filename — pct create accepts that form
    printf '%s' "$match"
    return 0
  fi

  say "Template not cached — updating appliance list and downloading"
  pveam update >/dev/null || true

  # pveam available columns: SECTION  NAME  (e.g. system  ubuntu-24.04-standard_24.04-2_amd64.tar.zst)
  # Do NOT use $1 — that is the section label "system", not the template file.
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

  # Prefer the storage:vztmpl/... ref from pveam list after download
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

install_mcs_into_ct() {
  say "Installing Python and MCS inside CT $CTID"
  pct exec "$CTID" -- bash -lc '
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv ca-certificates curl
    mkdir -p /opt/mcs
  '

  if [[ -n "$MCS_SRC" ]]; then
    [[ -d "$MCS_SRC" ]] || die "MCS_SRC is not a directory: $MCS_SRC"
    say "Copying MCS from $MCS_SRC"
    tar -C "$MCS_SRC" -cf - . | pct exec "$CTID" -- tar -C /opt/mcs -xf -
  else
    say "Cloning MCS from $REPO_URL"
    pct exec "$CTID" -- bash -lc "
      set -euo pipefail
      export DEBIAN_FRONTEND=noninteractive
      apt-get install -y -qq git
      rm -rf /tmp/mc-src
      git clone --depth 1 '$REPO_URL' /tmp/mc-src
      cp -a /tmp/mc-src/Apps/Master_Control_Server/Server_Component/. /opt/mcs/
      rm -rf /tmp/mc-src
    "
  fi

  pct exec "$CTID" -- bash -lc '
    set -euo pipefail
    cd /opt/mcs
    python3 -m venv /opt/mcs/.venv
    /opt/mcs/.venv/bin/pip install -q --upgrade pip
    if [[ -f pyproject.toml ]]; then
      /opt/mcs/.venv/bin/pip install -q .
    else
      /opt/mcs/.venv/bin/pip install -q fastapi "uvicorn[standard]" httpx
    fi
  '

  pct exec "$CTID" -- bash -lc "cat > /etc/systemd/system/mcs.service <<'UNIT'
[Unit]
Description=Master Control Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/mcs
EnvironmentFile=-/etc/mcs.env
ExecStart=/opt/mcs/.venv/bin/uvicorn main:app --host 0.0.0.0 --port ${MCS_PORT}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT"

  pct exec "$CTID" -- bash -lc "
    set -euo pipefail
    umask 077
    cat > /etc/mcs.env <<EOF
MCS_API_TOKEN=${MCS_API_TOKEN}
CENTRAL_PRIMARY_URL=
CENTRAL_SECONDARY_URL=
EOF
    systemctl daemon-reload
    systemctl enable mcs
    systemctl restart mcs
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
# Only the ostemplate path may be on stdout; status lines go to stderr via say().
if [[ -z "$TEMPLATE_REF" || "$TEMPLATE_REF" == *$'\n'* || "${#TEMPLATE_REF}" -gt 255 ]]; then
  die "Bad ostemplate from resolve_template (len=${#TEMPLATE_REF}): ${TEMPLATE_REF:0:120}"
fi

if [[ -z "$MCS_API_TOKEN" ]]; then
  MCS_API_TOKEN="$(generate_token)"
fi

cat <<EOF

This will create a Master Control Server LXC on this Proxmox node:

  CTID            $CTID
  Name            $CT_NAME
  Hostname        $HOSTNAME
  Template        $TEMPLATE_REF
  CPU             ${CORES} cores
  Memory          ${MEMORY_MB} MiB
  Disk            ${DISK_SIZE}G on ${STORAGE}
  Bridge          ${BRIDGE}
  Port            ${MCS_PORT}
  Root password   ${ROOT_PASSWORD}
  Start after     $([[ "$START_CT" == "1" ]] && echo yes || echo no)
  Source          $([[ -n "$MCS_SRC" ]] && echo "$MCS_SRC" || echo "git $REPO_URL")

EOF

if [[ "$SKIP_CONFIRM" != "1" ]]; then
  say "Starting in 5 seconds. Press Ctrl-C to cancel."
  sleep 5
fi

say "Creating CT $CTID ($CT_NAME)"
pct create "$CTID" "$TEMPLATE_REF" \
  --hostname "$HOSTNAME" \
  --memory "$MEMORY_MB" \
  --cores "$CORES" \
  --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp" \
  --storage "$STORAGE" \
  --rootfs "${STORAGE}:${DISK_SIZE}" \
  --unprivileged 1 \
  --features nesting=1 \
  --onboot 1 \
  --ostype ubuntu \
  --password "$ROOT_PASSWORD" \
  --description "Mission Control — Master Control Server"

# Human-friendly name in the UI (pct create uses hostname; set notes/name if supported)
pct set "$CTID" --hostname "$HOSTNAME" >/dev/null

# Ensure password is set even if --password was ignored on this PVE version
say "Starting CT $CTID"
pct start "$CTID"
sleep 2
echo "root:${ROOT_PASSWORD}" | pct exec "$CTID" -- chpasswd

say "Waiting for network"
CT_IP="$(wait_for_network)" || die "CT started but no IP yet. Check DHCP on ${BRIDGE}, then: pct enter ${CTID}"

install_mcs_into_ct

say "Checking /health"
if pct exec "$CTID" -- curl -fsS "http://127.0.0.1:${MCS_PORT}/health" >/dev/null; then
  say "MCS health check OK"
else
  say "Health check not ready yet — give it a few seconds and curl from your PC"
fi

cat <<EOF

Done. CT $CTID ($CT_NAME) is ready.

Console / SSH login:
  user: root
  password: ${ROOT_PASSWORD}
  (or from the Proxmox host: pct enter ${CTID})

Put these values into Home Assistant Core Configurator / secrets.yaml:

  cc_master_control_server:       http://${CT_IP}:${MCS_PORT}
  cc_master_control_server_token: ${MCS_API_TOKEN}

Quick checks:
  curl http://${CT_IP}:${MCS_PORT}/health
  pct enter ${CTID}
  systemctl status mcs

Next: Docs/Master Control Server Config Steps.md (paste into HA secrets, restart CC seed).

EOF
