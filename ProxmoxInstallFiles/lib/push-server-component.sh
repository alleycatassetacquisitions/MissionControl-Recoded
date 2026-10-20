#!/usr/bin/env bash
# Push a Server_Component tree into an existing CT and restart its systemd unit.
# Does NOT recreate the CT or touch /etc/*.env tokens.
#
# Usage (on Proxmox host):
#   CTID=120 UNIT=mcs DEST=/opt/mcs SRC=/path/to/Server_Component \
#     bash ProxmoxInstallFiles/lib/push-server-component.sh
#
# Optional: EXCLUDE_GLOBS="*.pyc __pycache__ .venv"

set -euo pipefail

CTID="${CTID:?CTID required}"
UNIT="${UNIT:?UNIT required (systemd unit name)}"
DEST="${DEST:?DEST required (path inside CT)}"
SRC="${SRC:?SRC required (host path to Server_Component)}"

say() { printf '\n==> %s\n' "$*" >&2; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

command -v pct >/dev/null 2>&1 || die "Run on the Proxmox host"
[[ -d "$SRC" ]] || die "SRC not a directory: $SRC"
pct status "$CTID" >/dev/null 2>&1 || die "CT $CTID not found"

say "Pushing $SRC → CT $CTID:$DEST"
pct exec "$CTID" -- mkdir -p "$DEST"
tar -C "$SRC" \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='.git' \
  -cf - . | pct exec "$CTID" -- tar -C "$DEST" -xf -

# Reinstall deps if a venv + requirements/pyproject exists
if pct exec "$CTID" -- test -x "${DEST}/.venv/bin/pip"; then
  say "Refreshing Python deps in CT $CTID"
  pct exec "$CTID" -- bash -lc "
    set -e
    cd '$DEST'
    if [[ -f pyproject.toml ]]; then
      .venv/bin/pip install -q -e '.[prod]' 2>/dev/null || .venv/bin/pip install -q -e .
    elif [[ -f requirements.txt ]]; then
      .venv/bin/pip install -q -r requirements.txt
    fi
  " || say "pip refresh skipped/failed — continuing"
fi

say "Restarting $UNIT"
pct exec "$CTID" -- systemctl restart "$UNIT"
sleep 1
pct exec "$CTID" -- systemctl is-active "$UNIT" >/dev/null \
  && say "$UNIT is active" \
  || say "WARN: $UNIT may still be starting"

echo "MC_OUT_CTID=${CTID}"
echo "MC_OUT_UNIT=${UNIT}"
echo "MC_OUT_DEST=${DEST}"
