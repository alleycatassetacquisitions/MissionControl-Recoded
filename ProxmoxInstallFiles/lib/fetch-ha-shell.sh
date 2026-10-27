#!/usr/bin/env bash
# Download custom-sidebar + card-mod into HomeAssist/www/mc-shell/ for venue
# installs (Mission Control sidebar title without requiring a live HACS download).
#
# Usage (from repo root or any cwd):
#   bash ProxmoxInstallFiles/lib/fetch-ha-shell.sh [dest_dir]
#
# Default dest: <repo>/HomeAssist/www/mc-shell

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEST="${1:-${REPO_ROOT}/HomeAssist/www/mc-shell}"

SIDEBAR_VER="${CUSTOM_SIDEBAR_VER:-v17.3.0}"
CARDMOD_VER="${CARD_MOD_VER:-v4.2.1}"

SIDEBAR_URL="https://github.com/elchininet/custom-sidebar/releases/download/${SIDEBAR_VER}/custom-sidebar-plugin.js"
CARDMOD_URL="https://cdn.jsdelivr.net/gh/thomasloven/lovelace-card-mod@${CARDMOD_VER}/card-mod.js"

say() { printf '==> %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

mkdir -p "$DEST"

download() {
  local url="$1" out="$2"
  if [[ -f "$out" && "${FORCE_FETCH:-0}" != "1" ]]; then
    say "Keeping existing $(basename "$out")"
    return 0
  fi
  say "Fetching $(basename "$out")"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "$out" "$url" || return 1
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "$out" "$url" || return 1
  else
    die "Need curl or wget to fetch HA shell plugins"
  fi
  [[ -s "$out" ]] || return 1
}

download "$SIDEBAR_URL" "${DEST}/custom-sidebar-plugin.js" \
  || die "Failed to download custom-sidebar (${SIDEBAR_URL})"
download "$CARDMOD_URL" "${DEST}/card-mod.js" \
  || die "Failed to download card-mod (${CARDMOD_URL})"

cat > "${DEST}/VERSIONS.txt" <<EOF
custom-sidebar ${SIDEBAR_VER}
lovelace-card-mod ${CARDMOD_VER}
fetched_at $(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

say "HA shell plugins ready in ${DEST}"
