#!/usr/bin/env bash
# Build a venue install bundle on a workstation (or CI).
#
# Output: dist/mission-control-venue/  and  dist/mission-control-venue.tar.gz
#          dist/SHA256SUMS  dist/install-mission-control.sh (thin bootstrap)
#
# Optional: SKIP_PANEL_BUILD=1  RELEASE=venue-local  COMMIT=dirty

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST="${REPO_ROOT}/dist"
STAGE="${DIST}/mission-control-venue"
SKIP_PANEL_BUILD="${SKIP_PANEL_BUILD:-0}"
RELEASE="${RELEASE:-venue-local-$(date -u +%Y%m%d)}"
COMMIT="${COMMIT:-$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo dirty)}"

say() { printf '\n==> %s\n' "$*" >&2; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# shellcheck source=lib/mc-install-common.sh
source "${SCRIPT_DIR}/lib/mc-install-common.sh"

say "Staging venue bundle → $STAGE"
rm -rf "$STAGE"
mkdir -p "$STAGE"

copy_tree() {
  local src="$1" dest="$2"
  [[ -e "$src" ]] || return 0
  mkdir -p "$(dirname "$dest")"
  if [[ -d "$src" ]]; then
    mkdir -p "$dest"
    # Prefer rsync; fall back to tar
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --delete \
        --exclude '.venv' --exclude '__pycache__' --exclude 'node_modules' \
        --exclude '.git' --exclude '.pytest_cache' --exclude '*.pyc' \
        "${src}/" "${dest}/"
    else
      tar -C "$src" \
        --exclude='.venv' --exclude='__pycache__' --exclude='node_modules' \
        --exclude='.git' --exclude='.pytest_cache' \
        -cf - . | tar -C "$dest" -xf -
    fi
  else
    cp -a "$src" "$dest"
  fi
}

if [[ "$SKIP_PANEL_BUILD" != "1" ]]; then
  PANEL="${REPO_ROOT}/Libraries/Shared_HA_Helpers/panel_kit"
  if [[ -f "${PANEL}/package.json" ]]; then
    say "Building panel_kit"
    (cd "$PANEL" && npm ci && npm run build) || (cd "$PANEL" && npm install && npm run build)
  else
    say "panel_kit missing — skipping build"
  fi
fi

say "Fetching HA shell plugins (custom-sidebar + card-mod) into HomeAssist/www/mc-shell"
bash "${SCRIPT_DIR}/lib/fetch-ha-shell.sh" "${REPO_ROOT}/HomeAssist/www/mc-shell" \
  || die "Could not fetch mc-shell plugins (need network once when packaging)"

say "Copying trees"
copy_tree "$REPO_ROOT/ProxmoxInstallFiles" "$STAGE/ProxmoxInstallFiles"
copy_tree "$REPO_ROOT/Apps" "$STAGE/Apps"
copy_tree "$REPO_ROOT/Libraries" "$STAGE/Libraries"
copy_tree "$REPO_ROOT/HomeAssist" "$STAGE/HomeAssist"
[[ -f "$REPO_ROOT/README.md" ]] && cp "$REPO_ROOT/README.md" "$STAGE/"

say "Writing manifest"
mc_write_manifest "$STAGE" "$COMMIT" "$RELEASE"

# Thin bootstrap that downloads (or uses local) and runs the orchestrator
cat > "${STAGE}/install-mission-control.sh" <<'BOOT'
#!/usr/bin/env bash
# Venue bootstrap — run on Proxmox host.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MC_SRC_ROOT="${MC_SRC_ROOT:-$HERE}"
if [[ ! -f "${HERE}/ProxmoxInstallFiles/install-mission-control.sh" ]]; then
  echo "ERROR: incomplete bundle (missing ProxmoxInstallFiles/install-mission-control.sh)" >&2
  exit 1
fi
# Normalize CRLF if copied from Windows
sed -i 's/\r$//' "${HERE}/ProxmoxInstallFiles/"*.sh "${HERE}/ProxmoxInstallFiles/lib/"*.sh 2>/dev/null || true
exec bash "${HERE}/ProxmoxInstallFiles/install-mission-control.sh" "$@"
BOOT
chmod +x "${STAGE}/install-mission-control.sh"

# Also place a downloadable thin bootstrap in dist/ for releases/latest/download/
mkdir -p "$DIST"
cat > "${DIST}/install-mission-control.sh" <<'BOOT2'
#!/usr/bin/env bash
# Thin online bootstrap — downloads the venue tarball then runs the orchestrator.
set -euo pipefail
REPO="${MC_RELEASE_REPO:-alleycatassetacquisitions/MissionControl-Recoded}"
BASE="${MC_RELEASE_DOWNLOAD_BASE:-https://github.com/${REPO}/releases/latest/download}"
DEST="${MC_DOWNLOAD_DIR:-/root/mission-control-download}"
mkdir -p "$DEST"
echo "==> Downloading mission-control-venue.tar.gz"
curl -fsSL ${GH_TOKEN:+-H "Authorization: Bearer ${GH_TOKEN}"} \
  -o "$DEST/mission-control-venue.tar.gz" "$BASE/mission-control-venue.tar.gz"
if curl -fsSL ${GH_TOKEN:+-H "Authorization: Bearer ${GH_TOKEN}"} \
  -o "$DEST/SHA256SUMS" "$BASE/SHA256SUMS" 2>/dev/null; then
  (cd "$DEST" && sha256sum -c SHA256SUMS --ignore-missing)
fi
rm -rf "$DEST/extract"
mkdir -p "$DEST/extract"
tar -xzf "$DEST/mission-control-venue.tar.gz" -C "$DEST/extract"
ROOT="$(find "$DEST/extract" -maxdepth 3 -name manifest.json | head -1 | xargs -r dirname)"
[[ -n "$ROOT" ]] || { echo "ERROR: bad tarball"; exit 1; }
rm -rf /root/mission-control-src
mkdir -p /root/mission-control-src
if command -v rsync >/dev/null 2>&1; then
  rsync -a "$ROOT"/ /root/mission-control-src/
else
  tar -C "$ROOT" -cf - . | tar -C /root/mission-control-src -xf -
fi
export MC_SRC_ROOT=/root/mission-control-src
sed -i 's/\r$//' /root/mission-control-src/ProxmoxInstallFiles/*.sh \
  /root/mission-control-src/ProxmoxInstallFiles/lib/*.sh 2>/dev/null || true
exec bash /root/mission-control-src/ProxmoxInstallFiles/install-mission-control.sh "$@"
BOOT2
chmod +x "${DIST}/install-mission-control.sh"

say "Creating tarball"
(cd "$DIST" && tar -czf mission-control-venue.tar.gz mission-control-venue)
(cd "$DIST" && sha256sum mission-control-venue.tar.gz install-mission-control.sh > SHA256SUMS)

say "Done"
echo "  Bundle dir:  $STAGE"
echo "  Tarball:     $DIST/mission-control-venue.tar.gz"
echo "  Checksums:   $DIST/SHA256SUMS"
echo "  Release:     $RELEASE  commit=$COMMIT"
echo
echo "Offline deploy:"
echo "  scp -r $STAGE root@<proxmox>:/root/"
echo "  # on Proxmox:"
echo "  bash /root/mission-control-venue/install-mission-control.sh"
