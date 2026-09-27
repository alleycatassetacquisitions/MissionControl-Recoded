#!/usr/bin/env bash
##############################################################################
# install-server.sh — AlleycatTV content server setup for Debian/Ubuntu LXC
#
# Installs: nginx, Python 3 venv, FastAPI/uvicorn
# Does NOT install MQTT clients — Home Assistant owns MQTT commands.
#
# Usage (run as root inside the LXC after copying Server_Component):
#   sudo bash setup/install-server.sh
##############################################################################
set -euo pipefail

INSTALL_DIR="/opt/alleycattv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_SRC="$DEPLOY_ROOT/app"
REQ_FILE="$DEPLOY_ROOT/requirements.txt"
[[ -f "$REQ_FILE" ]] || REQ_FILE="$APP_SRC/requirements.txt"

echo "============================================"
echo "  AlleycatTV Content Server Install"
echo "============================================"
echo ""
echo "  Deploy root: $DEPLOY_ROOT"
echo ""

read -rp "Max upload size in MB (default 500): " MAX_UPLOAD_MB
MAX_UPLOAD_MB="${MAX_UPLOAD_MB:-500}"

echo ""
echo "Configuration:"
echo "  Max upload:     ${MAX_UPLOAD_MB} MB"
echo "  MQTT:           none (Home Assistant publishes commands)"
echo ""
read -rp "Continue? [y/N]: " CONFIRM
[[ "${CONFIRM,,}" == "y" ]] || { echo "Aborted."; exit 0; }

echo ""
echo "Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    nginx python3 python3-pip python3-venv curl openssh-server

systemctl enable --now ssh 2>/dev/null || true

if ! id alleycattv &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin alleycattv
    echo "Created system user: alleycattv"
fi

echo "Creating directory structure at $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"/{media/{videos,photos,announcements,bumpers},server,venv}
touch "$INSTALL_DIR/devices.json" 2>/dev/null || true
chown -R alleycattv:alleycattv "$INSTALL_DIR"

echo "Setting up Python venv..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$REQ_FILE" -q

echo "Copying server app files..."
rm -rf "$INSTALL_DIR/server/app"
cp -r "$APP_SRC" "$INSTALL_DIR/server/"
# Ensure runtime can import app.config overrides via env; keep shipped config.py
export ALLEYCATV_MAX_UPLOAD_MB="$MAX_UPLOAD_MB"
# Write a small env file for systemd
cat > "$INSTALL_DIR/alleycattv.env" <<EOF
ALLEYCATV_MAX_UPLOAD_MB=${MAX_UPLOAD_MB}
ALLEYCATV_MEDIA=/opt/alleycattv/media
ALLEYCATV_PLAYLISTS=/opt/alleycattv/playlists.json
ALLEYCATV_ZONES=/opt/alleycattv/broadcast_groups.json
ALLEYCATV_DEVICES=/opt/alleycattv/devices.json
ALLEYCATV_SETTINGS=/opt/alleycattv/settings.json
EOF

chown -R alleycattv:alleycattv "$INSTALL_DIR/server" "$INSTALL_DIR/alleycattv.env"

# nginx
if [[ -f "$DEPLOY_ROOT/nginx/alleycattv.conf" ]]; then
    cp "$DEPLOY_ROOT/nginx/alleycattv.conf" /etc/nginx/sites-available/alleycattv
    ln -sfn /etc/nginx/sites-available/alleycattv /etc/nginx/sites-enabled/alleycattv
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl reload nginx
fi

# systemd
if [[ -f "$DEPLOY_ROOT/alleycattv-server.service" ]]; then
    cp "$DEPLOY_ROOT/alleycattv-server.service" /etc/systemd/system/alleycattv-server.service
    # Ensure EnvironmentFile is used
    if ! grep -q EnvironmentFile /etc/systemd/system/alleycattv-server.service; then
        sed -i '/\[Service\]/a EnvironmentFile=/opt/alleycattv/alleycattv.env' \
            /etc/systemd/system/alleycattv-server.service
    fi
    systemctl daemon-reload
    systemctl enable --now alleycattv-server
fi

echo ""
echo "AlleycatTV content server installed."
echo "  Health:  curl http://127.0.0.1/health"
echo "  Manage:  http://<host>/manage"
echo "  Set Core Configurator key 'alleycattv' to this host URL."
echo "  Playback MQTT is owned by Home Assistant — do not point this LXC at Mosquitto."
