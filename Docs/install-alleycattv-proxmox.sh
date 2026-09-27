#!/usr/bin/env bash
# Create an AlleycatTV content-server LXC on this Proxmox node.
#
# Run on the Proxmox HOST shell (the node, not a guest). Matches
# Docs/AlleycatTV Config Steps.md
#
# Phone walkthrough: open the node Shell in the Proxmox UI, paste:
#   bash install-alleycattv-proxmox.sh
#
# Optional environment overrides:
#   CTID=130 STORAGE=local-lvm TEMPLATE_STORAGE=local BRIDGE=vmbr0
#   CORES=2 MEMORY_MB=2048 DISK_SIZE=60 START_CT=1
#   ATV_SRC=/path/to/Server_Component
#   REPO_URL=https://github.com/alleycatassetacquisitions/MissionContorl-Recoded.git
#   ROOT_PASSWORD=alleycat
#   TEMPLATE=ubuntu-24.04-standard  SKIP_CONFIRM=0
# CTID is optional. If omitted (or already in use), the next free ID is used.
#
# This LXC does NOT run Mosquitto. Home Assistant owns MQTT commands.

set -euo pipefail

REQUESTED_CTID="${CTID:-}"
CT_NAME="${CT_NAME:-AlleycatTV}"
HOSTNAME="${HOSTNAME_ATV:-alleycattv}"
STORAGE="${STORAGE:-local-lvm}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
BRIDGE="${BRIDGE:-vmbr0}"
CORES="${CORES:-2}"
MEMORY_MB="${MEMORY_MB:-2048}"
DISK_SIZE="${DISK_SIZE:-60}"
START_CT="${START_CT:-1}"
TEMPLATE_PREFIX="${TEMPLATE:-ubuntu-24.04-standard}"
ATV_SRC="${ATV_SRC:-}"
REPO_URL="${REPO_URL:-https://github.com/alleycatassetacquisitions/MissionContorl-Recoded.git}"
ROOT_PASSWORD="${ROOT_PASSWORD:-alleycat}"
SKIP_CONFIRM="${SKIP_CONFIRM:-0}"
MAX_UPLOAD_MB="${MAX_UPLOAD_MB:-500}"

say() { printf '\n==> %s\n' "$*" >&2; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

require_proxmox() {
  command -v pct >/dev/null 2>&1 || die "pct not found. Run this on the Proxmox node shell, not inside a guest."
  command -v pveam >/dev/null 2>&1 || die "pveam not found. This does not look like a Proxmox host."
  command -v pvesm >/dev/null 2>&1 || die "pvesm not found. This does not look like a Proxmox host."
}

ctid_in_use() {
  pct status "$1" >/dev/null 2>&1
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

install_atv_into_ct() {
  say "Installing nginx + AlleycatTV content server inside CT $CTID"
  pct exec "$CTID" -- bash -lc '
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq nginx python3 python3-pip python3-venv ca-certificates curl
    mkdir -p /opt/alleycattv/{media/{videos,photos,announcements,bumpers},server,venv}
    if ! id alleycattv &>/dev/null; then
      useradd --system --no-create-home --shell /usr/sbin/nologin alleycattv
    fi
  '

  if [[ -n "$ATV_SRC" ]]; then
    [[ -d "$ATV_SRC" ]] || die "ATV_SRC is not a directory: $ATV_SRC"
    say "Copying AlleycatTV Server_Component from $ATV_SRC"
    tar -C "$ATV_SRC" -cf - . | pct exec "$CTID" -- tar -C /opt/alleycattv/server -xf -
  else
    say "Cloning AlleycatTV from $REPO_URL"
    pct exec "$CTID" -- bash -lc "
      set -euo pipefail
      export DEBIAN_FRONTEND=noninteractive
      apt-get install -y -qq git
      rm -rf /tmp/mc-src
      git clone --depth 1 '$REPO_URL' /tmp/mc-src
      cp -a /tmp/mc-src/Apps/AlleycatTV/Server_Component/. /opt/alleycattv/server/
      rm -rf /tmp/mc-src
    "
  fi

  pct exec "$CTID" -- bash -lc "
    set -euo pipefail
    REQ=/opt/alleycattv/server/requirements.txt
    [[ -f \"\$REQ\" ]] || REQ=/opt/alleycattv/server/app/requirements.txt
    python3 -m venv /opt/alleycattv/venv
    /opt/alleycattv/venv/bin/pip install -q --upgrade pip
    /opt/alleycattv/venv/bin/pip install -q -r \"\$REQ\"
    cat > /opt/alleycattv/alleycattv.env <<EOF
ALLEYCATV_MAX_UPLOAD_MB=${MAX_UPLOAD_MB}
ALLEYCATV_MEDIA=/opt/alleycattv/media
ALLEYCATV_PLAYLISTS=/opt/alleycattv/playlists.json
ALLEYCATV_ZONES=/opt/alleycattv/broadcast_groups.json
ALLEYCATV_DEVICES=/opt/alleycattv/devices.json
ALLEYCATV_SETTINGS=/opt/alleycattv/settings.json
EOF
    chown -R alleycattv:alleycattv /opt/alleycattv
  "

  # systemd unit
  pct exec "$CTID" -- bash -lc 'cat > /etc/systemd/system/alleycattv-server.service <<'"'"'UNIT'"'"'
[Unit]
Description=AlleycatTV content server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=-/opt/alleycattv/alleycattv.env
User=alleycattv
WorkingDirectory=/opt/alleycattv/server
ExecStart=/opt/alleycattv/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --access-log
Restart=on-failure
RestartSec=5
ReadWritePaths=/opt/alleycattv

[Install]
WantedBy=multi-user.target
UNIT'

  # nginx
  pct exec "$CTID" -- bash -lc '
    set -euo pipefail
    if [[ -f /opt/alleycattv/server/nginx/alleycattv.conf ]]; then
      cp /opt/alleycattv/server/nginx/alleycattv.conf /etc/nginx/sites-available/alleycattv
    else
      cat > /etc/nginx/sites-available/alleycattv <<'"'"'NGX'"'"'
server {
    listen 80;
    server_name _;
    location /media/ {
        alias /opt/alleycattv/media/;
        autoindex off;
        sendfile on;
        client_max_body_size 512M;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 120s;
        client_max_body_size 512M;
    }
    location /health { proxy_pass http://127.0.0.1:8000/health; }
    location /manage {
        proxy_pass http://127.0.0.1:8000/manage;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
    location / { return 404; }
}
NGX
    fi
    ln -sfn /etc/nginx/sites-available/alleycattv /etc/nginx/sites-enabled/alleycattv
    rm -f /etc/nginx/sites-enabled/default
    nginx -t
    systemctl enable nginx
    systemctl restart nginx
    systemctl daemon-reload
    systemctl enable --now alleycattv-server
  '
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

cat <<EOF

This will create an AlleycatTV content-server LXC on this Proxmox node:

  CTID            $CTID
  Name            $CT_NAME
  Hostname        $HOSTNAME
  Template        $TEMPLATE_REF
  CPU             ${CORES} cores
  Memory          ${MEMORY_MB} MiB
  Disk            ${DISK_SIZE}G on ${STORAGE}
  Bridge          ${BRIDGE}
  HTTP            port 80 (nginx → uvicorn :8000)
  MQTT            none (Home Assistant publishes commands)
  Root password   ${ROOT_PASSWORD}
  Start after     $([[ "$START_CT" == "1" ]] && echo yes || echo no)
  Source          $([[ -n "$ATV_SRC" ]] && echo "$ATV_SRC" || echo "git $REPO_URL")

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
  --description "Mission Control — AlleycatTV content server (no MQTT)"

say "Starting CT $CTID"
pct start "$CTID"
sleep 2
echo "root:${ROOT_PASSWORD}" | pct exec "$CTID" -- chpasswd

say "Waiting for network"
CT_IP="$(wait_for_network)" || die "CT started but no IP yet. Check DHCP on ${BRIDGE}, then: pct enter ${CTID}"

install_atv_into_ct

say "Checking /health"
if pct exec "$CTID" -- curl -fsS "http://127.0.0.1/health" >/dev/null; then
  say "AlleycatTV health check OK"
else
  say "Health check not ready yet — give it a few seconds and curl from your PC"
fi

cat <<EOF

Done. CT $CTID ($CT_NAME) is ready.

Console / SSH login:
  user: root
  password: ${ROOT_PASSWORD}
  (or from the Proxmox host: pct enter ${CTID})

Put this into Home Assistant Core Configurator / secrets.yaml:

  cc_alleycattv: http://${CT_IP}

Quick checks:
  curl http://${CT_IP}/health
  # expect mqtt: false
  open http://${CT_IP}/manage

Next:
  1. Docs/AlleycatTV Config Steps.md — HA deploy + Pi flash
  2. Docs/Home Assistant Config Steps.md — Phase 6

EOF
