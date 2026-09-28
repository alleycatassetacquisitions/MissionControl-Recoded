#!/usr/bin/env bash
##############################################################################
# install-server.sh — Galactic Bounty Network FastAPI server (Ubuntu 24.04)
#
# Installs: python3 venv, uvicorn, systemd service
# Creates:  /opt/gbn/
#
# Usage (as root, after scp of the Server_Component tree):
#   bash /opt/gbn-deploy/setup/install-server.sh
##############################################################################
set -euo pipefail

INSTALL_DIR="/opt/gbn"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================"
echo "  Galactic Bounty Network Server Install"
echo "============================================"
echo ""
echo "  Deploy root: $DEPLOY_ROOT"
echo ""

HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname)"
DEFAULT_PUBLIC="http://${HOSTNAME_FQDN}:8100"
read -rp "Public base URL for poster links [${DEFAULT_PUBLIC}]: " PUBLIC_BASE
PUBLIC_BASE="${PUBLIC_BASE:-$DEFAULT_PUBLIC}"
PUBLIC_BASE="${PUBLIC_BASE%/}"

read -rp "Master Control Server base URL (blank = no live overlay): " MCS_BASE
MCS_BASE="${MCS_BASE%/}"
read -rp "MCS API token (blank if MCS_BASE empty): " MCS_TOKEN

echo ""
echo "Configuration:"
echo "  Install dir:   $INSTALL_DIR"
echo "  Public base:   $PUBLIC_BASE"
echo "  MCS:           ${MCS_BASE:-<none>}"
echo ""
read -rp "Continue? [y/N]: " CONFIRM
[[ "${CONFIRM,,}" == "y" ]] || { echo "Aborted."; exit 0; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv curl ca-certificates

if ! id gbn &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin gbn
    echo "Created system user: gbn"
fi

mkdir -p "$INSTALL_DIR"/{media/videos,media/assets/neocorp,media/assets/animations,media/assets/marks,data,.venv,setup}
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/.venv/bin/pip" install -r "$DEPLOY_ROOT/requirements.txt" -q

rm -rf "$INSTALL_DIR/app"
cp -a "$DEPLOY_ROOT/app" "$INSTALL_DIR/"
cp -f "$DEPLOY_ROOT/requirements.txt" "$INSTALL_DIR/"
if [[ -d "$DEPLOY_ROOT/media/assets/neocorp" ]]; then
  cp -a "$DEPLOY_ROOT/media/assets/neocorp/." "$INSTALL_DIR/media/assets/neocorp/"
fi
chown -R gbn:gbn "$INSTALL_DIR"

cat > /etc/gbn.env <<EOF
GBN_HOST=0.0.0.0
GBN_PORT=8100
GBN_PUBLIC_BASE=${PUBLIC_BASE}
GBN_MEDIA=${INSTALL_DIR}/media
GBN_DATA=${INSTALL_DIR}/data
GBN_POSTERS=${INSTALL_DIR}/data/posters.json
GBN_MCS_BASE=${MCS_BASE}
GBN_MCS_TOKEN=${MCS_TOKEN}
EOF
chmod 640 /etc/gbn.env
chown root:gbn /etc/gbn.env

UNIT_SRC="$DEPLOY_ROOT/gbn-server.service"
if [[ -f "$UNIT_SRC" ]]; then
  cp -f "$UNIT_SRC" /etc/systemd/system/gbn.service
else
  cat > /etc/systemd/system/gbn.service <<'UNIT'
[Unit]
Description=Galactic Bounty Network poster server
After=network.target

[Service]
Type=simple
User=gbn
Group=gbn
WorkingDirectory=/opt/gbn
EnvironmentFile=-/etc/gbn.env
ExecStart=/opt/gbn/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8100
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
fi

systemctl daemon-reload
systemctl enable --now gbn
echo ""
echo "GBN listening on ${PUBLIC_BASE}"
echo "Health: curl -s ${PUBLIC_BASE}/health"
echo "Set Core Configurator key gbn to: ${PUBLIC_BASE}"
