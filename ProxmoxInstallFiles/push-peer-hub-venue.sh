#!/usr/bin/env bash
# On the Proxmox host: push flat MCS + GBN trees, then optionally smoke-test fan-out.
#
# Required (or defaults below): flat trees already staged on the host.
#   MCS_SRC=/root/mcs-src   # must contain main.py at top level
#   GBN_SRC=/root/gbn-src   # must contain app/ at top level
#
# Optional smoke test (set SMOKE=1):
#   CENTRAL_PRIMARY  MCS_URL  GBN_URL  HOST_CLOCK_URL
#
# Example:
#   SMOKE=1 CENTRAL_PRIMARY=https://central.example \
#     MCS_URL=http://10.0.0.10:8700 GBN_URL=http://10.0.0.11:8100 \
#     HOST_CLOCK_URL=http://10.0.0.1:8721 \
#     bash /root/push-peer-hub-venue.sh
#
set -euo pipefail

PUSH="${PUSH_HELPER:-/root/push-server-component.sh}"
MCS_SRC="${MCS_SRC:-/root/mcs-src}"
GBN_SRC="${GBN_SRC:-/root/gbn-src}"
MCS_CTID="${MCS_CTID:-102}"
GBN_CTID="${GBN_CTID:-101}"
SMOKE="${SMOKE:-0}"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
say() { printf '\n==> %s\n' "$*" >&2; }

[[ -x "$PUSH" || -f "$PUSH" ]] || die "missing $PUSH"
[[ -f "$MCS_SRC/main.py" ]] || die "MCS SRC not flat (need $MCS_SRC/main.py) — avoid nested Server_Component/"
[[ -d "$GBN_SRC/app" ]] || die "GBN SRC not flat (need $GBN_SRC/app/) — avoid nested Server_Component/"

# Hygiene: leftover wrong units from a CTID swap (safe no-op if absent)
for pair in "${MCS_CTID}:gbn.service" "${GBN_CTID}:mcs.service"; do
  ctid="${pair%%:*}"
  unit="${pair##*:}"
  if pct exec "$ctid" -- test -f "/etc/systemd/system/${unit}" 2>/dev/null; then
    say "Removing leftover ${unit} from CT ${ctid}"
    pct exec "$ctid" -- systemctl disable --now "$unit" 2>/dev/null || true
    pct exec "$ctid" -- rm -f "/etc/systemd/system/${unit}"
    pct exec "$ctid" -- systemctl daemon-reload
  fi
done

if pct exec "$GBN_CTID" -- grep -q 'PASTE_SAME_TOKEN_AS_MCS' /etc/gbn.env 2>/dev/null; then
  die "/etc/gbn.env still has placeholder PASTE_SAME_TOKEN_AS_MCS — set GBN_MCS_TOKEN to MCS token"
fi

say "Push MCS CT ${MCS_CTID}"
CTID="$MCS_CTID" UNIT=mcs DEST=/opt/mcs SRC="$MCS_SRC" bash "$PUSH"

say "Push GBN CT ${GBN_CTID}"
CTID="$GBN_CTID" UNIT=gbn DEST=/opt/gbn SRC="$GBN_SRC" bash "$PUSH"

# Tar push can leave /opt/gbn/data owned by root — restore service user ownership.
say "Fix GBN data ownership"
pct exec "$GBN_CTID" -- bash -lc '
  USER=$(systemctl show gbn -p User --value); USER=${USER:-gbn}
  chown -R "$USER:$USER" /opt/gbn/data /opt/gbn/media 2>/dev/null || true
'

say "Health"
pct exec "$MCS_CTID" -- curl -sf http://127.0.0.1:8700/health | head -c 200; echo
pct exec "$GBN_CTID" -- curl -sf http://127.0.0.1:8100/health | head -c 200; echo

if [[ "$SMOKE" != "1" ]]; then
  say "Skip smoke (set SMOKE=1 with CENTRAL_PRIMARY/MCS_URL/GBN_URL to test fan-out)"
  exit 0
fi

: "${CENTRAL_PRIMARY:?CENTRAL_PRIMARY required when SMOKE=1}"
: "${MCS_URL:?MCS_URL required when SMOKE=1}"
: "${GBN_URL:?GBN_URL required when SMOKE=1}"
HOST_CLOCK_URL="${HOST_CLOCK_URL:-}"

TOKEN="$(pct exec "$MCS_CTID" -- bash -lc "grep ^MCS_API_TOKEN= /etc/mcs.env | cut -d= -f2-")"
[[ -n "$TOKEN" ]] || die "MCS_API_TOKEN empty in /etc/mcs.env"

smoke_json=$(printf '{"central_primary":"%s","central_secondary":"","mcs_url":"%s","gbn_url":"%s","host_clock_url":"%s"}' \
  "$CENTRAL_PRIMARY" "$MCS_URL" "$GBN_URL" "$HOST_CLOCK_URL")

say "POST /config peer smoke"
pct exec "$MCS_CTID" -- curl -s -o /dev/null -w 'MCS /config HTTP %{http_code}\n' -X POST http://127.0.0.1:8700/config \
  -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \
  -d "$smoke_json"

say "GET /config/status"
pct exec "$MCS_CTID" -- curl -s -H "Authorization: Bearer ${TOKEN}" http://127.0.0.1:8700/config/status
echo

say "GBN journal (fan-out)"
pct exec "$GBN_CTID" -- journalctl -u gbn -n 30 --no-pager --since '2 min ago' \
  | grep -iE 'GBN /config|POST /config' || echo "(no GBN /config lines yet)"

say "Done — confirm last_fanout.gbn.ok in status JSON above"
