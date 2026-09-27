#!/usr/bin/env bash
##############################################################################
# install.sh â€” AlleycatTV player setup for Raspberry Pi OS Lite (no desktop)
#
# Installs a tiny Wayland kiosk (labwc) for HDMI, then mpv + Chromium kiosk
# for video/photo/live pages. Run as root on a fresh Lite image.
#
# Usage:
#   chmod +x install.sh
#   sudo ./install.sh
##############################################################################
set -euo pipefail

INSTALL_DIR="/opt/alleycattv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo ./install.sh" >&2
  exit 1
fi

TARGET_USER="${SUDO_USER:-$(logname 2>/dev/null || true)}"
if [[ -z "${TARGET_USER}" || "${TARGET_USER}" == "root" ]]; then
  read -rp "Linux username that will run the player: " TARGET_USER
fi
if ! id "$TARGET_USER" >/dev/null 2>&1; then
  echo "User '${TARGET_USER}' does not exist." >&2
  exit 1
fi
TARGET_UID="$(id -u "$TARGET_USER")"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"

echo "============================================"
echo "  AlleycatTV Player Setup (Lite + kiosk)"
echo "============================================"
echo ""
echo "  Service user: ${TARGET_USER} (uid ${TARGET_UID})"
echo ""

# ── Prompt for device configuration ──────────────────────────────────────────
read -rp "Pi ID (e.g. pi-lobby-1):                    " PI_ID
read -rp "Content server URL (e.g. http://alleycattv.local): " SERVER_URL
read -rp "MQTT broker (HAOS Mosquitto host):          " MQTT_IP
read -rp "MQTT username (leave blank if none):       " MQTT_USER
read -rsp "MQTT password (leave blank if none):      " MQTT_PASS
echo ""
read -rp "Optional Broadcast Group ID for playlist (blank until Phase 7): " BG_ID
read -rp "Photo interval (videos between photos, default 5): " PHOTO_INTERVAL
PHOTO_INTERVAL="${PHOTO_INTERVAL:-5}"

echo ""
echo "Configuration:"
echo "  PI_ID:          $PI_ID"
echo "  SERVER_URL:     $SERVER_URL"
echo "  MQTT_BROKER:    $MQTT_IP"
echo "  MQTT_USER:      ${MQTT_USER:-<none>}"
echo "  BROADCAST_GROUP:${BG_ID:-<none>}"
echo "  PHOTO_INTERVAL: $PHOTO_INTERVAL"
echo ""
read -rp "Continue? [y/N]: " CONFIRM
[[ "${CONFIRM,,}" == "y" ]] || { echo "Aborted."; exit 0; }

render_unit() {
  local src="$1"
  local dest="$2"
  sed -e "s|__USER__|${TARGET_USER}|g" \
      -e "s|__UID__|${TARGET_UID}|g" \
      -e "s|__HOME__|${TARGET_HOME}|g" \
      "$src" > "$dest"
}

# â”€â”€ System packages â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "Installing packages..."
apt-get update -qq
BASE_PKGS=(
  mpv python3 python3-pip python3-venv
  labwc seatd dbus-user-session
  fonts-liberation alsa-utils
)
apt-get install -y --no-install-recommends "${BASE_PKGS[@]}"
if ! apt-get install -y --no-install-recommends chromium; then
  apt-get install -y --no-install-recommends chromium-browser
fi

# HDMI / DRM access for the kiosk user
usermod -aG video,render,input,tty,audio "$TARGET_USER"
loginctl enable-linger "$TARGET_USER" >/dev/null 2>&1 || true
systemctl enable seatd >/dev/null 2>&1 || true
systemctl start seatd >/dev/null 2>&1 || true

# Console on tty1 would steal the display from labwc; SSH / Pi Connect still work.
systemctl disable --now getty@tty1.service >/dev/null 2>&1 || true

# â”€â”€ Create install directory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
mkdir -p "$INSTALL_DIR/kiosk"
mkdir -p "$INSTALL_DIR/cache/videos" "$INSTALL_DIR/cache/photos" "$INSTALL_DIR/cache/announcements"
mkdir -p /var/lib/alleycattv
chown -R "$TARGET_USER:$TARGET_USER" "$INSTALL_DIR/cache"
chown "$TARGET_USER:$TARGET_USER" /var/lib/alleycattv

# â”€â”€ Python venv + dependencies â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "Setting up Python environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q

# â”€â”€ Copy player + kiosk files â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
rm -rf "$INSTALL_DIR/alleycattv_player"
cp -r "$SCRIPT_DIR/alleycattv_player" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/kiosk/." "$INSTALL_DIR/kiosk/"
chmod +x "$INSTALL_DIR/kiosk/wait-wayland.sh"

# Install the Chromium kiosk extension (hides cursor + scrollbars on web pages)
if [[ -d "$SCRIPT_DIR/kiosk_ext" ]]; then
  rm -rf "$INSTALL_DIR/kiosk_ext"
  cp -r "$SCRIPT_DIR/kiosk_ext" "$INSTALL_DIR/"
  echo "Kiosk extension installed at $INSTALL_DIR/kiosk_ext"
fi

chown -R "$TARGET_USER:$TARGET_USER" "$INSTALL_DIR"

# ── Per-unit env (config.py already reads ALLEYCATV_* from environment) ──────
cat > /etc/alleycattv.env <<EOF
ALLEYCATV_PI_ID=$PI_ID
ALLEYCATV_BROADCAST_GROUP_ID=$BG_ID
ALLEYCATV_SERVER=$SERVER_URL
ALLEYCATV_MQTT=$MQTT_IP
ALLEYCATV_MQTT_PORT=1883
ALLEYCATV_MQTT_USER=$MQTT_USER
ALLEYCATV_MQTT_PASS=$MQTT_PASS
ALLEYCATV_PHOTO_INTERVAL=$PHOTO_INTERVAL
EOF
chmod 640 /etc/alleycattv.env
chown root:"$TARGET_USER" /etc/alleycattv.env

# Ensure player service loads the env file
if [[ -f /etc/systemd/system/alleycattv-player.service ]]; then
  :
fi

# ── systemd units ────────────────────────────────────────────────────────────
echo "Installing systemd services..."
render_unit "$SCRIPT_DIR/kiosk/alleycattv-kiosk.service.in" /etc/systemd/system/alleycattv-kiosk.service
render_unit "$SCRIPT_DIR/alleycattv-player.service.in" /etc/systemd/system/alleycattv-player.service
# Inject EnvironmentFile if missing
if ! grep -q 'alleycattv.env' /etc/systemd/system/alleycattv-player.service; then
  sed -i '/\[Service\]/a EnvironmentFile=/etc/alleycattv.env' \
    /etc/systemd/system/alleycattv-player.service
fi
systemctl daemon-reload
systemctl enable alleycattv-kiosk alleycattv-player
systemctl restart alleycattv-kiosk
sleep 2
systemctl restart alleycattv-player

echo ""
echo "============================================"
echo "  Install complete!"
echo "============================================"
echo "Kiosk:   systemctl status alleycattv-kiosk"
echo "Player:  systemctl status alleycattv-player"
echo "Logs:    journalctl -u alleycattv-kiosk -u alleycattv-player -f"
echo "Env:     /etc/alleycattv.env"
echo ""
echo "HDMI needs the labwc kiosk (no desktop). SSH and Pi Connect are unchanged."
echo "MQTT topics use mc/tv/… — Home Assistant is the only command publisher."
