#!/usr/bin/env bash
# Mission Control venue orchestrator — run on the Proxmox HOST.
#
# Online:   bash <(curl -fsSL …/install-mission-control.sh)   # thin bootstrap
# Offline:  bash /root/mission-control-venue/install-mission-control.sh
#
# Env overrides:
#   MC_SRC_ROOT  SKIP_HAOS=0  SKIP_CONFIRM=1  BRIDGE=vmbr0
#   CENTRAL_PRIMARY=  CENTRAL_SECONDARY=  SKIP_CENTRAL_PROMPT=0
#   PROXMOX_TOKEN_ID=  PROXMOX_TOKEN_SECRET=  PROXMOX_NODE=pve
#   (omit PROXMOX_TOKEN_SECRET to auto-create hass@pve!missioncontrol)
#   HAOS_IMAGE=/path/to/haos_ova-XX.qcow2.xz   # offline HAOS (no GitHub)
#   TEMPLATE=ubuntu-24.04-standard              # LXC ostemplate prefix
#   SKIP_PVE_HOST_PREP=0   SKIP_PVE_UPGRADE=0   # repos + nag + apt update/upgrade

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Prefer staged source root (bundle) over script-relative parent
if [[ -n "${MC_SRC_ROOT:-}" && -d "${MC_SRC_ROOT}/ProxmoxInstallFiles" ]]; then
  :
elif [[ -d "${SCRIPT_DIR}/../Apps" ]]; then
  MC_SRC_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
elif [[ -d /root/mission-control-src/ProxmoxInstallFiles ]]; then
  MC_SRC_ROOT=/root/mission-control-src
else
  MC_SRC_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi
export MC_SRC_ROOT

# shellcheck source=lib/mc-install-common.sh
source "${SCRIPT_DIR}/lib/mc-install-common.sh"

SKIP_HAOS="${SKIP_HAOS:-0}"
SKIP_CONFIRM="${SKIP_CONFIRM:-1}"
# RESUME=ha-deploy — skip guest create/pause; redeploy into HA using state file
RESUME="${RESUME:-}"
BRIDGE="${BRIDGE:-vmbr0}"
STORAGE="${STORAGE:-local-lvm}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
ROOT_PASSWORD="${ROOT_PASSWORD:-alleycat}"
PROXMOX_NODE="${PROXMOX_NODE:-pve}"

mc_require_proxmox

# Phase 0 — free updates + kill subscription nag (Docs/Proxmox Config Steps § B + § C)
# Runs on every full install and on RESUME=ha-deploy (idempotent). Skip: SKIP_PVE_HOST_PREP=1
mc_prepare_proxmox_host

mc_ensure_ha_keypair
mc_state_init_empty

HOST_IP="$(mc_host_ip "$BRIDGE")"
[[ -n "$HOST_IP" ]] || mc_die "Could not determine host IP on $BRIDGE"

# Offline venues: fail early with a clear message if no Ubuntu CT template is staged
if [[ "$RESUME" != "ha-deploy" ]]; then
  mc_check_offline_prereqs "$TEMPLATE_STORAGE" "${TEMPLATE:-ubuntu-24.04-standard}"
fi

export SKIP_CONFIRM STORAGE TEMPLATE_STORAGE BRIDGE ROOT_PASSWORD
# Pass through offline HAOS image / template prefix to child installers
[[ -n "${HAOS_IMAGE:-}" ]] && export HAOS_IMAGE
[[ -n "${TEMPLATE:-}" ]] && export TEMPLATE
[[ -n "${HAOS_VERSION:-}" ]] && export HAOS_VERSION

run_child() {
  local script="$1"
  shift
  local log
  log="$(mktemp /tmp/mc-child.XXXXXX.log)"
  mc_say "Running $(basename "$script")"
  set +e
  # Human output to stderr (still visible); capture MC_OUT_* on stdout for caller
  bash "$script" "$@" >"$log" 2>&1
  local rc=$?
  set -e
  # Show the log to the operator
  cat "$log" >&2
  [[ $rc -eq 0 ]] || mc_die "$(basename "$script") failed (exit $rc) — see $log"
  mc_parse_mc_out "$log"
  rm -f "$log"
}

capture_out() {
  # capture_out <component> < log lines with MC_OUT_*
  local component="$1"
  local url="" token="" ctid="" ip="" port="" host_clock=""
  while IFS= read -r line; do
    case "$line" in
      MC_OUT_URL=*) url="${line#MC_OUT_URL=}" ;;
      MC_OUT_TOKEN=*) token="${line#MC_OUT_TOKEN=}" ;;
      MC_OUT_CTID=*) ctid="${line#MC_OUT_CTID=}" ;;
      MC_OUT_VMID=*) ctid="${line#MC_OUT_VMID=}" ;;
      MC_OUT_IP=*) ip="${line#MC_OUT_IP=}" ;;
      MC_OUT_PORT=*) port="${line#MC_OUT_PORT=}" ;;
      MC_OUT_HOST_CLOCK_URL=*) host_clock="${line#MC_OUT_HOST_CLOCK_URL=}" ;;
    esac
  done
  python3 - "$MC_STATE_FILE" "$component" "$url" "$token" "$ctid" "$ip" "$port" "$host_clock" <<'PY'
import json, sys
path, key, url, token, ctid, ip, port, host_clock = sys.argv[1:9]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
svc = data.setdefault("services", {}).setdefault(key, {})
if url: svc["url"] = url
if token: svc["token"] = token
if ctid: svc["ctid"] = ctid
if ip: svc["ip"] = ip
if port: svc["port"] = port
if host_clock: svc["host_clock_url"] = host_clock
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
}

HA_IP=""
HAOS_VMID=""
DISCOVERED_HA_IP=""

if [[ "$RESUME" == "ha-deploy" ]]; then
  HA_IP="$(python3 -c "import json;print(json.load(open('$MC_STATE_FILE')).get('ha_ip',''))" 2>/dev/null || true)"
  [[ -n "$HA_IP" ]] || mc_die "RESUME=ha-deploy needs ha_ip in $MC_STATE_FILE"
  HOST_IP="$(python3 -c "import json;print(json.load(open('$MC_STATE_FILE')).get('host_ip','') or '')" 2>/dev/null || true)"
  [[ -n "$HOST_IP" ]] || HOST_IP="$(mc_host_ip "$BRIDGE")"
  mc_say "RESUME=ha-deploy — deploying into HA at ${HA_IP} (skipping LXC create)"
else

# ─── Phase 1: HAOS ───────────────────────────────────────────────────────────
if [[ "$SKIP_HAOS" != "1" ]]; then
  existing_ha="$(mc_find_haos_vmid)"
  if [[ -n "$existing_ha" ]]; then
    mc_say "Reusing existing Home-Assistant VM $existing_ha"
    HAOS_VMID="$existing_ha"
    qm set "$HAOS_VMID" --agent 1 >/dev/null 2>&1 || true
    mc_state_merge "{\"services\":{\"haos\":{\"ctid\":\"$existing_ha\"}}}"
  else
    out="$(run_child "${SCRIPT_DIR}/install-haos-proxmox.sh")"
    capture_out haos <<<"$out"
    HAOS_VMID="$(python3 -c "import json;print(json.load(open('$MC_STATE_FILE')).get('services',{}).get('haos',{}).get('ctid',''))" 2>/dev/null || true)"
    [[ -n "$HAOS_VMID" ]] || HAOS_VMID="$(mc_find_haos_vmid)"
  fi
else
  mc_say "SKIP_HAOS=1 — not creating HAOS VM"
  HAOS_VMID="$(mc_find_haos_vmid)"
fi

mc_say "Discovering Home Assistant LAN IP (guest agent / DNS / ARP)…"
DISCOVERED_HA_IP="$(mc_wait_for_ha_ip "$HAOS_VMID" 90 || true)"
if [[ -n "$DISCOVERED_HA_IP" ]]; then
  mc_say "Detected Home Assistant at ${DISCOVERED_HA_IP}"
  mc_state_merge "{\"services\":{\"haos\":{\"ip\":\"${DISCOVERED_HA_IP}\",\"ctid\":\"${HAOS_VMID}\"}}}"
else
  mc_say "Could not auto-detect HA IP yet — open the VM console or check your router DHCP list"
fi

# ─── Phase 2: Pause for onboard + SSH ────────────────────────────────────────
PUBKEY="$(cat "${MC_HA_KEY}.pub")"
HA_URL_HINT="http://homeassistant.local:8123"
if [[ -n "$DISCOVERED_HA_IP" ]]; then
  HA_URL_HINT="http://${DISCOVERED_HA_IP}:8123  (also http://homeassistant.local:8123)"
fi
cat <<EOF

══════════════════════════════════════════════════════════════════════════════
 PAUSE — Home Assistant onboarding + SSH
══════════════════════════════════════════════════════════════════════════════

Detected HA IP: ${DISCOVERED_HA_IP:-"(not detected yet — check VM console)"}
Open: ${HA_URL_HINT}

1. Finish onboarding in the browser.
2. Profile → enable Advanced Mode.
3. Settings → Add-ons → install **Terminal & SSH**:
   - Authorized Keys: paste the public key below (one line)
   - Network → port 22 → Save
   - Start the add-on
4. Confirm the HA LAN IP below (Enter accepts the detected value).

Public key for Terminal & SSH Authorized Keys:

${PUBKEY}

══════════════════════════════════════════════════════════════════════════════

EOF

HA_IP=""
while true; do
  if [[ -n "$DISCOVERED_HA_IP" ]]; then
    read -r -p "HA LAN IP [${DISCOVERED_HA_IP}] (Enter to accept, or 'q' to abort): " HA_IP
    [[ -z "$HA_IP" ]] && HA_IP="$DISCOVERED_HA_IP"
  else
    # Re-try discovery each prompt in case HA just got a lease
    DISCOVERED_HA_IP="$(mc_discover_ha_ip "$HAOS_VMID" || true)"
    if [[ -n "$DISCOVERED_HA_IP" ]]; then
      read -r -p "HA LAN IP [${DISCOVERED_HA_IP}] (Enter to accept, or 'q' to abort): " HA_IP
      [[ -z "$HA_IP" ]] && HA_IP="$DISCOVERED_HA_IP"
    else
      read -r -p "HA LAN IP (or 'q' to abort): " HA_IP
    fi
  fi
  [[ "$HA_IP" != "q" ]] || mc_die "Aborted by operator"
  [[ -n "$HA_IP" ]] || continue
  if mc_ha_ssh "$HA_IP" "true" 2>/dev/null; then
    mc_say "SSH to root@${HA_IP} OK"
    break
  fi
  echo "SSH failed — check Terminal & SSH is running and the key was pasted."
  # Refresh discovery for next attempt
  DISCOVERED_HA_IP="$(mc_discover_ha_ip "$HAOS_VMID" || true)"
done

mc_state_merge "{\"ha_ip\":\"${HA_IP}\",\"host_ip\":\"${HOST_IP}\",\"services\":{\"haos\":{\"ip\":\"${HA_IP}\",\"ctid\":\"${HAOS_VMID}\"}}}"

# ─── Phase 3: Companion LXCs ─────────────────────────────────────────────────
fi  # end RESUME!=ha-deploy early section — LXCs only when not resuming

if [[ "$RESUME" != "ha-deploy" ]]; then
# Companion LXCs (skipped on RESUME=ha-deploy)
# MCS
if python3 -c "import json;d=json.load(open('$MC_STATE_FILE'));s=d.get('services',{}).get('mcs',{});raise SystemExit(0 if s.get('url') else 1)" 2>/dev/null; then
  mc_say "MCS already in state — skipping create (use updater to refresh code)"
else
  out="$(
    MCS_SRC="${MC_SRC_ROOT}/Apps/Master_Control_Server/Server_Component" \
      run_child "${SCRIPT_DIR}/install-mcs-proxmox.sh"
  )"
  capture_out mcs <<<"$out"
fi

MCS_URL="$(python3 -c "import json;print(json.load(open('$MC_STATE_FILE'))['services']['mcs']['url'])")"
MCS_TOKEN="$(python3 -c "import json;print(json.load(open('$MC_STATE_FILE'))['services']['mcs'].get('token',''))")"

# AlleycatTV
if ! python3 -c "import json;d=json.load(open('$MC_STATE_FILE'));raise SystemExit(0 if d.get('services',{}).get('alleycattv',{}).get('url') else 1)" 2>/dev/null; then
  out="$(
    ATV_SRC="${MC_SRC_ROOT}/Apps/AlleycatTV/Server_Component" \
      run_child "${SCRIPT_DIR}/install-alleycattv-proxmox.sh"
  )"
  capture_out alleycattv <<<"$out"
fi

# GBN (with MCS wiring)
if ! python3 -c "import json;d=json.load(open('$MC_STATE_FILE'));raise SystemExit(0 if d.get('services',{}).get('gbn',{}).get('url') else 1)" 2>/dev/null; then
  out="$(
    GBN_SRC="${MC_SRC_ROOT}/Apps/Galactic_Bounty_Network/Server_Component" \
    GBN_MCS_BASE="${MCS_URL}" \
    GBN_MCS_TOKEN="${MCS_TOKEN}" \
      run_child "${SCRIPT_DIR}/install-gbn-proxmox.sh"
  )"
  capture_out gbn <<<"$out"
fi

# Net Time
if ! python3 -c "import json;d=json.load(open('$MC_STATE_FILE'));raise SystemExit(0 if d.get('services',{}).get('net_time',{}).get('url') else 1)" 2>/dev/null; then
  out="$(
    NET_TIME_SRC="${MC_SRC_ROOT}/Apps/Net_Time/Server_Component" \
      run_child "${SCRIPT_DIR}/install-net-time-proxmox.sh"
  )"
  capture_out net_time <<<"$out"
fi

# ─── Phase 3b: Venue update agent ────────────────────────────────────────────
VENUE_TOKEN="$(python3 -c "import json;print(json.load(open('$MC_STATE_FILE')).get('venue_updater_token',''))" 2>/dev/null || true)"
if [[ -z "$VENUE_TOKEN" ]]; then
  VENUE_TOKEN="$(mc_generate_token)"
fi
mc_say "Installing venue update agent on :${MC_VENUE_UPDATER_PORT}"
install -m 0755 "${SCRIPT_DIR}/venue_update_agent.py" /usr/local/sbin/mc-venue-update
umask 077
cat > /etc/mc-venue-update.env <<EOF
VENUE_UPDATER_TOKEN=${VENUE_TOKEN}
VENUE_UPDATER_PORT=${MC_VENUE_UPDATER_PORT}
MC_STATE_FILE=${MC_STATE_FILE}
MC_SRC_ROOT=${MC_SRC_ROOT}
MC_UPDATE_SCRIPT=${MC_SRC_ROOT}/ProxmoxInstallFiles/update-mission-control.sh
EOF
cat > /etc/systemd/system/mc-venue-update.service <<'UNIT'
[Unit]
Description=Mission Control venue update agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=-/etc/mc-venue-update.env
ExecStart=/usr/bin/python3 /usr/local/sbin/mc-venue-update
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now mc-venue-update
systemctl restart mc-venue-update

VENUE_URL="http://${HOST_IP}:${MC_VENUE_UPDATER_PORT}"
mc_state_merge "$(python3 - <<PY
import json
print(json.dumps({
  "venue_updater_token": "${VENUE_TOKEN}",
  "services": {
    "venue_updater": {"url": "${VENUE_URL}", "token": "${VENUE_TOKEN}"}
  }
}))
PY
)"

# Record component digests from local manifest if present
if [[ -f "${MC_SRC_ROOT}/manifest.json" ]]; then
  python3 - "$MC_STATE_FILE" "${MC_SRC_ROOT}/manifest.json" <<'PY'
import json, sys
from datetime import datetime, timezone
sp, mp = sys.argv[1:3]
with open(sp, encoding="utf-8") as f: state = json.load(f)
with open(mp, encoding="utf-8") as f: man = json.load(f)
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
state["release"] = man.get("release")
state["commit"] = man.get("commit")
state["last_updated_at"] = now
comps = state.setdefault("components", {})
for k, v in (man.get("components") or {}).items():
    comps[k] = {"digest": v.get("digest"), "updated_at": now}
with open(sp, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)
    f.write("\n")
PY
fi

fi  # end RESUME!=ha-deploy LXC + agent block

# ─── Phase 4: Deploy to HA ───────────────────────────────────────────────────
[[ -n "$HA_IP" ]] || HA_IP="$(python3 -c "import json;print(json.load(open('$MC_STATE_FILE')).get('ha_ip',''))")"
[[ -n "$HA_IP" ]] || mc_die "No HA_IP — cannot deploy components"

# Auto Proxmox token + Central URLs before secrets (venue-friendly; no UI clicks)
mc_ensure_proxmox_api_token
mc_prompt_central_urls

bash "${SCRIPT_DIR}/lib/deploy-ha-components.sh" "$HA_IP" "$MC_SRC_ROOT"

# Render secrets.yaml
mc_say "Writing /config/secrets.yaml"
python3 - "$MC_STATE_FILE" "$HA_IP" "$HOST_IP" "${CENTRAL_PRIMARY:-}" "${CENTRAL_SECONDARY:-}" \
  "${PROXMOX_NODE}" "${PROXMOX_TOKEN_ID:-}" "${PROXMOX_TOKEN_SECRET:-}" <<'PY' | mc_ha_ssh "$HA_IP" "cat > /config/secrets.yaml"
import json, sys
sp, ha_ip, host_ip, cpri, csec, pnode, ptid, psec = sys.argv[1:9]
with open(sp, encoding="utf-8") as f:
    st = json.load(f)
svc = st.get("services") or {}
def u(k): return (svc.get(k) or {}).get("url") or ""
def t(k): return (svc.get(k) or {}).get("token") or ""
lines = [
    "# Generated by install-mission-control.sh — do not commit",
    f"cc_master_control_server: {u('mcs')}",
    f"cc_master_control_server_token: {t('mcs')}",
    f"cc_central_primary: {cpri or 'https://your-cloud-player-api.example.com'}",
    # Empty secondary is valid (no LAN mirror). Quote so YAML keeps "".
    f"cc_central_secondary: {json.dumps(csec or '')}",
    f"cc_alleycattv: {u('alleycattv')}",
    f"cc_gbn: {u('gbn')}",
    f"cc_proxmox: https://{host_ip}:8006",
    f"cc_proxmox_node: {pnode or 'pve'}",
    f"cc_proxmox_token_id: {ptid or 'hass@pve!missioncontrol'}",
    f"cc_proxmox_token_secret: {psec or 'REPLACE_ME_RUN_INSTALLER_AGAIN'}",
    "cc_rtsp: rtsp://192.168.1.50:554/stream1",
    "cc_rtsp_label: Live RTSP",
    "cc_rtsp_enabled: false",
    f"cc_net_time: {u('net_time')}",
    f"cc_net_time_token: {t('net_time')}",
    f"cc_venue_updater: {u('venue_updater')}",
    f"cc_venue_updater_token: {t('venue_updater')}",
]
print("\n".join(lines) + "\n")
PY

# Merge configuration.yaml seed on the Proxmox host (HA SSH add-on has no python3)
mc_say "Merging configuration.yaml seed"
mc_ha_ssh "$HA_IP" "cp -a /config/configuration.yaml /config/configuration.yaml.bak-mc || true"
MERGE_DIR="$(mktemp -d /tmp/mc-ha-merge.XXXXXX)"
scp -i "$MC_HA_KEY" \
  -o StrictHostKeyChecking=accept-new \
  -o UserKnownHostsFile=/root/.ssh/mc-ha-known_hosts \
  "root@${HA_IP}:/config/configuration.yaml" \
  "${MERGE_DIR}/configuration.yaml" 2>/dev/null \
  || printf 'default_config:\n' >"${MERGE_DIR}/configuration.yaml"
cp "${MC_SRC_ROOT}/HomeAssist/configuration.yaml" "${MERGE_DIR}/mc-seed.yaml"
python3 - "${MERGE_DIR}/configuration.yaml" "${MERGE_DIR}/mc-seed.yaml" "${MERGE_DIR}/out.yaml" <<'PY'
from pathlib import Path
import re
import sys
live_path, seed_path, out_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
text = live_path.read_text(encoding="utf-8") if live_path.exists() else ""
seed_text = seed_path.read_text(encoding="utf-8")
if "default_config:" not in text:
    text = "default_config:\n\n" + text
if "mission-control-seed" not in text:
    text = text.rstrip() + "\n\n# mission-control-seed\n" + seed_text + "\n"
    print("appended Mission Control seed", flush=True)
else:
    # Seed already merged — still ensure install-only YAML domains exist for import.
    added = []
    for domain in (
        "registration",
        "digital_node_nexus",
        "alleycattv",
        "broadcast_group_controller",
        "gbn",
        "bug_buster",
        "game_master",
        "net_time",
    ):
        if re.search(rf"(?m)^{re.escape(domain)}\s*:", text):
            continue
        text = text.rstrip() + f"\n\n{domain}: {{}}\n"
        added.append(domain)
    # Point shell plugins at vendored /local/mc-shell (replaces old HACS paths).
    text2 = text.replace(
        "/hacsfiles/custom-sidebar/custom-sidebar-plugin.js",
        "/local/mc-shell/custom-sidebar-plugin.js",
    ).replace(
        "/hacsfiles/lovelace-card-mod/card-mod.js",
        "/local/mc-shell/card-mod.js",
    )
    if text2 != text:
        text = text2
        print("rewrote frontend shell URLs to /local/mc-shell", flush=True)
    if added:
        print("appended missing domains: " + ", ".join(added), flush=True)
    else:
        print("seed already present — domains ok", flush=True)
out_path.write_text(text, encoding="utf-8")
PY
scp -i "$MC_HA_KEY" \
  -o StrictHostKeyChecking=accept-new \
  -o UserKnownHostsFile=/root/.ssh/mc-ha-known_hosts \
  "${MERGE_DIR}/out.yaml" \
  "root@${HA_IP}:/config/configuration.yaml"
rm -rf "$MERGE_DIR"

# Drop stale Core Configurator entry so YAML+secrets re-import (covers RESUME redeploy)
mc_ha_force_cc_reseed "$HA_IP"
sleep 15

mc_say "Waiting for HA to come back"
for _ in $(seq 1 36); do
  if mc_ha_ssh "$HA_IP" "ha core info" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

# ─── Phase 5: Mosquitto + MQTT + theme + HACS ─────────────────────────────────
mc_ha_bootstrap_mqtt "$HA_IP" || true
mc_ha_bootstrap_hacs "$HA_IP" || true
mc_ha_apply_alleycat_theme "$HA_IP" || true
# Theme storage is read at core start — one more restart after HACS unpack
mc_say "Restarting HA core to load theme + HACS"
mc_ha_ssh "$HA_IP" "ha core restart" || true
sleep 15
for _ in $(seq 1 24); do
  if mc_ha_ssh "$HA_IP" "ha core info" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done
# Re-apply theme service now that core is up
mc_ha_apply_alleycat_theme "$HA_IP" || true

# ─── Done ────────────────────────────────────────────────────────────────────
python3 - "$MC_STATE_FILE" "${PROXMOX_TOKEN_ID:-}" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    st = json.load(f)
svc = st.get("services") or {}
ptid = sys.argv[2] if len(sys.argv) > 2 else ""
print("""
══════════════════════════════════════════════════════════════════════════════
 Mission Control venue install complete
══════════════════════════════════════════════════════════════════════════════
""")
print(f"  State file:  {sys.argv[1]}")
print(f"  HA IP:       {st.get('ha_ip')}")
print(f"  Release:     {st.get('release')}")
print(f"  Proxmox tok: {ptid or '(see secrets.yaml)'}")
for key in ("mcs", "alleycattv", "gbn", "net_time", "venue_updater"):
    s = svc.get(key) or {}
    print(f"  {key:14} {s.get('url','')}")
print("""
Automated for the venue operator:
  • Proxmox no-subscription repos + subscription-nag patch (hard-refresh :8006)
  • Registration + Digital Node Nexus config entries (YAML import)
  • Core Configurator reseed from secrets.yaml
  • Proxmox API token (hass@pve!missioncontrol) written to secrets
  • Mosquitto add-on + MQTT integration (best effort)
  • Alleycat theme set as default (light + dark)
  • Sidebar title **Mission Control** (vendored custom-sidebar)
  • HACS component (when HA has internet) — authorize once in the UI

Still optional / venue-specific:
  1. Settings → Devices & services → Add **Proxmox VE** (monitoring sensors)
     Host=<proxmox-ip> port 8006 · user hass · realm PVE · token missioncontrol
     (same secret as Core Configurator — printed above / in secrets.yaml)
  2. Settings → Devices & services → Add **HACS** (if not prompted) → GitHub device code once
  3. Flash AlleycatTV Pis / point FDN firmware at HA MQTT (alleycatTV / alleycat)

Updates later:
  Core Configurator → Check for GitHub Update
  or: bash /root/mission-control-src/ProxmoxInstallFiles/update-mission-control.sh --check
""")
PY
