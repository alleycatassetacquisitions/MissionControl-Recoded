#!/usr/bin/env bash
# Shared helpers for Mission Control venue install / update (sourced, not executed).
# shellcheck disable=SC2034

MC_STATE_FILE="${MC_STATE_FILE:-/root/mission-control-install-state.json}"
MC_SRC_ROOT="${MC_SRC_ROOT:-/root/mission-control-src}"
MC_HA_KEY="${MC_HA_KEY:-/root/.ssh/mc-ha}"
MC_VENUE_UPDATER_PORT="${MC_VENUE_UPDATER_PORT:-8722}"
MC_RELEASE_REPO="${MC_RELEASE_REPO:-alleycatassetacquisitions/MissionControl-Recoded}"
MC_RELEASE_API="${MC_RELEASE_API:-https://api.github.com/repos/${MC_RELEASE_REPO}/releases/latest}"
MC_RELEASE_DOWNLOAD_BASE="${MC_RELEASE_DOWNLOAD_BASE:-https://github.com/${MC_RELEASE_REPO}/releases/latest/download}"

mc_say() { printf '\n==> %s\n' "$*" >&2; }
mc_die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

mc_python() {
  # Prefer a real interpreter (Windows Store stubs break `command -v python`).
  local cand
  for cand in python3 python py; do
    if command -v "$cand" >/dev/null 2>&1; then
      if [[ "$cand" == "py" ]]; then
        if py -3 -c "import sys" >/dev/null 2>&1; then
          echo "py -3"
          return 0
        fi
      elif "$cand" -c "import sys" >/dev/null 2>&1; then
        command -v "$cand"
        return 0
      fi
    fi
  done
  mc_die "python3 (or py -3) is required"
}

mc_require_proxmox() {
  command -v pct >/dev/null 2>&1 || mc_die "pct not found. Run on the Proxmox node shell."
  command -v pveam >/dev/null 2>&1 || mc_die "pveam not found. This does not look like a Proxmox host."
}

mc_host_ip() {
  local bridge="${1:-vmbr0}" ip=""
  ip="$(ip -4 -o addr show dev "$bridge" 2>/dev/null | awk '{print $4}' | head -1 | cut -d/ -f1 || true)"
  if [[ -z "$ip" ]]; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  fi
  printf '%s' "$ip"
}

mc_find_haos_vmid() {
  qm list 2>/dev/null | awk '/Home-Assistant/{print $1; exit}' || true
}

mc_discover_ha_ip() {
  # Best-effort HA LAN IP. Tries QEMU guest agent, then mDNS-ish names, then ARP.
  # Usage: mc_discover_ha_ip [vmid]
  local vmid="${1:-}" ip="" raw=""
  if [[ -z "$vmid" ]]; then
    vmid="$(mc_find_haos_vmid)"
  fi

  if [[ -n "$vmid" ]]; then
    qm set "$vmid" --agent 1 >/dev/null 2>&1 || true
    # Guest agent JSON (when HAOS qemu-ga is up)
    raw="$(qm guest cmd "$vmid" network-get-interfaces 2>/dev/null || true)"
    if [[ -n "$raw" ]]; then
      ip="$(python3 -c "
import json,sys,re
try:
    data=json.load(sys.stdin)
except Exception:
    sys.exit(0)
# pvesh/qm may wrap as {'result':[...]} or bare list
if isinstance(data, dict) and 'result' in data:
    data=data['result']
if not isinstance(data, list):
    sys.exit(0)
for iface in data:
    name=str(iface.get('name') or '')
    if name in ('lo','docker0') or name.startswith('veth') or name.startswith('br-'):
        continue
    for addr in iface.get('ip-addresses') or []:
        if addr.get('ip-address-type')!='ipv4':
            continue
        a=str(addr.get('ip-address') or '')
        if a.startswith('127.') or a.startswith('172.30.') or a.startswith('172.17.'):
            continue
        print(a)
        raise SystemExit
" <<<"$raw" 2>/dev/null || true)"
    fi
  fi

  if [[ -z "$ip" ]]; then
    # Resolve common HA hostnames if the host can
    for host in homeassistant.local homeassistant hass; do
      ip="$(getent ahostsv4 "$host" 2>/dev/null | awk '{print $1; exit}' || true)"
      [[ -n "$ip" ]] && break
      if command -v avahi-resolve >/dev/null 2>&1; then
        ip="$(avahi-resolve -4 -n "$host" 2>/dev/null | awk '{print $2; exit}' || true)"
        [[ -n "$ip" ]] && break
      fi
    done
  fi

  if [[ -z "$ip" && -n "$vmid" ]]; then
    # Last resort: MAC from VM config → ARP / bridge fdb
    local mac
    mac="$(qm config "$vmid" 2>/dev/null | awk -F'[=,]' '/^net0:/{for(i=1;i<=NF;i++) if($i ~ /^[0-9a-fA-F:]{17}$/){print tolower($i); exit}}' || true)"
    if [[ -z "$mac" ]]; then
      mac="$(qm config "$vmid" 2>/dev/null | sed -n 's/.*macaddr=\([0-9A-Fa-f:][0-9A-Fa-f:]*\).*/\1/p' | head -1 | tr 'A-F' 'a-f' || true)"
    fi
    if [[ -n "$mac" ]]; then
      ip="$(ip neigh show 2>/dev/null | awk -v m="$mac" 'tolower($5)==m {print $1; exit}' || true)"
      if [[ -z "$ip" ]]; then
        ip="$(bridge fdb show 2>/dev/null | awk -v m="$mac" 'tolower($1)==m {print $0}' | head -1 || true)"
        # fdb doesn't give IP; ignore
        ip=""
      fi
    fi
  fi

  printf '%s' "$ip"
}

mc_wait_for_ha_ip() {
  # Poll discovery for up to N seconds. Prints progress on stderr; IP on stdout.
  local vmid="${1:-}" max_sec="${2:-120}" i ip=""
  for i in $(seq 1 "$max_sec"); do
    ip="$(mc_discover_ha_ip "$vmid")"
    if [[ -n "$ip" ]]; then
      printf '%s' "$ip"
      return 0
    fi
    if (( i % 15 == 0 )); then
      mc_say "Still waiting for Home Assistant IP… (${i}s)"
    fi
    sleep 1
  done
  return 1
}

mc_generate_token() {
  openssl rand -hex 24 2>/dev/null || head -c 48 /dev/urandom | xxd -p | head -c 48
}

mc_ensure_ha_keypair() {
  if [[ ! -f "$MC_HA_KEY" ]]; then
    mkdir -p "$(dirname "$MC_HA_KEY")"
    ssh-keygen -t ed25519 -N "" -f "$MC_HA_KEY" -C "mission-control-proxmox" >/dev/null
    mc_say "Generated HA deploy key at $MC_HA_KEY"
  fi
}

mc_ha_ssh() {
  local ha_ip="$1"
  shift
  ssh -i "$MC_HA_KEY" \
    -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile=/root/.ssh/mc-ha-known_hosts \
    -o ConnectTimeout=10 \
    "root@${ha_ip}" "$@"
}

mc_ha_scp() {
  local ha_ip="$1"
  shift
  scp -i "$MC_HA_KEY" \
    -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile=/root/.ssh/mc-ha-known_hosts \
    "$@" "root@${ha_ip}:/config/"
}

mc_ha_rsync_tree() {
  # Usage: mc_ha_rsync_tree <ha_ip> <local_src_dir> <remote_rel_under_config>
  # Prefer tar|ssh — HA Terminal & SSH add-on usually has no rsync binary.
  local ha_ip="$1" src="$2" dest_rel="$3"
  [[ -d "$src" ]] || return 0
  mc_ha_ssh "$ha_ip" "mkdir -p /config/${dest_rel}"
  if tar -C "$src" -cf - . | mc_ha_ssh "$ha_ip" "tar -C /config/${dest_rel} -xf -"; then
    return 0
  fi
  # Optional fallback if tar path failed and both sides somehow support rsync
  if command -v rsync >/dev/null 2>&1; then
    rsync -az -e "ssh -i ${MC_HA_KEY} -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.ssh/mc-ha-known_hosts" \
      "${src}/" "root@${ha_ip}:/config/${dest_rel}/" \
      && return 0
  fi
  return 1
}

mc_state_init_empty() {
  if [[ ! -f "$MC_STATE_FILE" ]]; then
    printf '%s\n' '{"version":1,"components":{},"services":{}}' >"$MC_STATE_FILE"
  fi
}

mc_json_get() {
  # mc_json_get <file> <python_expr_on_data>
  local file="$1" expr="$2"
  python3 - "$file" "$expr" <<'PY'
import json, sys
path, expr = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
print(eval(expr, {"data": data}))
PY
}

mc_state_merge() {
  # Merge a JSON object string into state file (shallow top-level + nested services/components).
  local patch_json="$1"
  python3 - "$MC_STATE_FILE" "$patch_json" <<'PY'
import json, sys
path, patch_s = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
except FileNotFoundError:
    data = {"version": 1, "components": {}, "services": {}}
patch = json.loads(patch_s)
for k, v in patch.items():
    if k in ("components", "services") and isinstance(v, dict):
        data.setdefault(k, {}).update(v)
    else:
        data[k] = v
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
}

mc_digest_tree() {
  # Stable sha256 of sorted file contents under paths (relative to MC_SRC_ROOT or absolute).
  local root="${1:-$MC_SRC_ROOT}"
  shift
  python3 - "$root" "$@" <<'PY'
import hashlib, os, sys
root = sys.argv[1]
paths = sys.argv[2:]
h = hashlib.sha256()
files = []
for p in paths:
    abs_p = p if os.path.isabs(p) else os.path.join(root, p)
    if not os.path.exists(abs_p):
        continue
    if os.path.isfile(abs_p):
        files.append(abs_p)
        continue
    for dirpath, _, filenames in os.walk(abs_p):
        for name in filenames:
            if name.endswith((".pyc", ".map")) or name == "__pycache__":
                continue
            files.append(os.path.join(dirpath, name))
for fp in sorted(files):
    rel = os.path.relpath(fp, root).replace("\\", "/")
    h.update(rel.encode())
    with open(fp, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
print("sha256:" + h.hexdigest())
PY
}

mc_write_manifest() {
  # Write manifest.json under $1 (bundle root).
  local dest="$1"
  local commit="${2:-unknown}"
  local release="${3:-local}"
  local created
  created="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # shellcheck disable=SC2086
  eval "$(mc_python)" - "$dest" "$commit" "$release" "$created" <<'PY'
import hashlib, json, os, sys
dest, commit, release, created = sys.argv[1:5]

def digest(paths):
    h = hashlib.sha256()
    files = []
    for p in paths:
        abs_p = os.path.join(dest, p) if not os.path.isabs(p) else p
        if not os.path.exists(abs_p):
            continue
        if os.path.isfile(abs_p):
            files.append(abs_p)
            continue
        for dirpath, dirnames, filenames in os.walk(abs_p):
            dirnames[:] = [d for d in dirnames if d != "__pycache__" and d != "node_modules"]
            for name in filenames:
                if name.endswith((".pyc", ".map")):
                    continue
                files.append(os.path.join(dirpath, name))
    for fp in sorted(set(files)):
        rel = os.path.relpath(fp, dest).replace("\\", "/")
        h.update(rel.encode())
        with open(fp, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
    return "sha256:" + h.hexdigest()

components = {
    "mcs": {
        "digest": digest(["Apps/Master_Control_Server/Server_Component"]),
        "paths": ["Apps/Master_Control_Server/Server_Component"],
    },
    "alleycattv": {
        "digest": digest(["Apps/AlleycatTV/Server_Component"]),
        "paths": ["Apps/AlleycatTV/Server_Component"],
    },
    "gbn": {
        "digest": digest(["Apps/Galactic_Bounty_Network/Server_Component"]),
        "paths": ["Apps/Galactic_Bounty_Network/Server_Component"],
    },
    "net_time": {
        "digest": digest(["Apps/Net_Time/Server_Component"]),
        "paths": ["Apps/Net_Time/Server_Component"],
    },
    "ha": {
        "digest": digest([
            "Apps/Core_Configurator/HA_Component",
            "Apps/Registration/HA_Component",
            "Apps/Digital_Node_Nexus/HA_Component",
            "Apps/AlleycatTV/HA_Component",
            "Apps/Broadcast_Group_Controller/HA_Component",
            "Apps/Galactic_Bounty_Network/HA_Component",
            "Apps/Bug_Buster/HA_Component",
            "Apps/Game_Master/HA_Component",
            "Apps/Net_Time/HA_Component",
            "Libraries/Shared_HA_Helpers/HA_Component",
            "HomeAssist",
        ]),
        "paths": ["Apps/*/HA_Component", "Libraries/Shared_HA_Helpers", "HomeAssist"],
    },
    "scripts": {
        "digest": digest(["ProxmoxInstallFiles"]),
        "paths": ["ProxmoxInstallFiles"],
    },
}
manifest = {
    "release": release,
    "commit": commit,
    "created_at": created,
    "components": components,
}
with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
print(os.path.join(dest, "manifest.json"))
PY
}

mc_parse_mc_out() {
  # Grep MC_OUT_* from a log file into KEY=value on stdout.
  local log="$1"
  grep -E '^MC_OUT_[A-Z0-9_]+=' "$log" || true
}

mc_fetch_latest_release() {
  # Download venue tarball + checksums into $1 directory. Prints extract path.
  local dest="$1"
  mkdir -p "$dest"
  local tar_url sums_url
  tar_url="${MC_RELEASE_DOWNLOAD_BASE}/mission-control-venue.tar.gz"
  sums_url="${MC_RELEASE_DOWNLOAD_BASE}/SHA256SUMS"
  mc_say "Downloading venue release from $tar_url"
  curl -fsSL ${GH_TOKEN:+-H "Authorization: Bearer ${GH_TOKEN}"} -o "${dest}/mission-control-venue.tar.gz" "$tar_url" \
    || mc_die "Failed to download mission-control-venue.tar.gz — use offline BUNDLE= path"
  if curl -fsSL ${GH_TOKEN:+-H "Authorization: Bearer ${GH_TOKEN}"} -o "${dest}/SHA256SUMS" "$sums_url" 2>/dev/null; then
    (cd "$dest" && sha256sum -c SHA256SUMS --ignore-missing) || mc_die "Checksum verification failed"
  else
    mc_say "SHA256SUMS not available — skipping checksum verify"
  fi
  mkdir -p "${dest}/extract"
  tar -xzf "${dest}/mission-control-venue.tar.gz" -C "${dest}/extract"
  # Find the tree that contains ProxmoxInstallFiles or manifest.json
  local root
  root="$(find "${dest}/extract" -maxdepth 3 -type f -name manifest.json 2>/dev/null | head -1 | xargs -r dirname)"
  if [[ -z "$root" ]]; then
    root="$(find "${dest}/extract" -maxdepth 3 -type d -name ProxmoxInstallFiles 2>/dev/null | head -1 | xargs -r dirname)"
  fi
  [[ -n "$root" ]] || mc_die "Could not find venue tree inside tarball"
  printf '%s' "$root"
}

# ─── Venue automation helpers ────────────────────────────────────────────────

mc_prepare_proxmox_host() {
  # First-step host prep (Docs/Proxmox Config Steps.md § B + § C):
  #   • Switch APT from pve-enterprise → pve-no-subscription (free updates)
  #   • Patch + persist the "No valid subscription" UI nag
  #   • apt-get update + dist-upgrade (latest patches) unless SKIP_PVE_UPGRADE=1
  # Skip entire prep with SKIP_PVE_HOST_PREP=1.
  if [[ "${SKIP_PVE_HOST_PREP:-0}" == "1" ]]; then
    mc_say "Skipping Proxmox host prep (SKIP_PVE_HOST_PREP=1)"
    return 0
  fi

  mc_say "Proxmox host prep — no-subscription repos + nag patch + update/upgrade"

  local suite
  suite="$(. /etc/os-release 2>/dev/null; printf '%s' "${VERSION_CODENAME:-}")"
  if [[ -z "$suite" ]]; then
    if [[ -f /etc/debian_version ]]; then
      case "$(cut -d. -f1 /etc/debian_version 2>/dev/null || true)" in
        13) suite=trixie ;;
        12) suite=bookworm ;;
        11) suite=bullseye ;;
        *) suite=bookworm ;;
      esac
    else
      suite=bookworm
    fi
  fi
  mc_say "Detected Debian suite: ${suite}"

  # Disable enterprise (VE 9 .sources and classic .list; Ceph enterprise too)
  for f in /etc/apt/sources.list.d/pve-enterprise.sources \
           /etc/apt/sources.list.d/ceph.sources \
           /etc/apt/sources.list.d/ceph-enterprise.sources; do
    if [[ -f "$f" ]]; then
      sed -i 's/^Enabled: yes/Enabled: no/i' "$f" 2>/dev/null || true
      # If the file has no Enabled: line, append one under Types: deb blocks is messy —
      # commenting Types works as a fallback for stub files.
      if grep -qiE '^Types:' "$f" && ! grep -qiE '^Enabled:' "$f"; then
        sed -i 's/^Types:/Enabled: no\nTypes:/' "$f" 2>/dev/null || true
      fi
      mc_say "Disabled enterprise source file: $f"
    fi
  done
  for f in /etc/apt/sources.list.d/pve-enterprise.list \
           /etc/apt/sources.list.d/ceph.list; do
    if [[ -f "$f" ]]; then
      sed -i -E 's/^[[:space:]]*deb/#deb/' "$f" 2>/dev/null || true
      mc_say "Commented enterprise list: $f"
    fi
  done

  # Free no-subscription repo (deb822 on VE 9 / trixie; classic list on older)
  local keyring="/usr/share/keyrings/proxmox-archive-keyring.gpg"
  if [[ ! -f "$keyring" ]]; then
    keyring="/etc/apt/trusted.gpg.d/proxmox-release-${suite}.gpg"
  fi
  if [[ "$suite" == "trixie" ]] || [[ -f /etc/apt/sources.list.d/pve-enterprise.sources ]] \
    || [[ -f /etc/apt/sources.list.d/debian.sources ]]; then
    cat > /etc/apt/sources.list.d/proxmox.sources <<EOF
Types: deb
URIs: http://download.proxmox.com/debian/pve
Suites: ${suite}
Components: pve-no-subscription
Signed-By: ${keyring}
EOF
    rm -f /etc/apt/sources.list.d/pve-no-subscription.list
    mc_say "Wrote /etc/apt/sources.list.d/proxmox.sources (pve-no-subscription)"
  else
    echo "deb http://download.proxmox.com/debian/pve ${suite} pve-no-subscription" \
      > /etc/apt/sources.list.d/pve-no-subscription.list
    mc_say "Wrote /etc/apt/sources.list.d/pve-no-subscription.list"
  fi

  # Subscription nag patch + APT hook so upgrades re-apply it
  local libjs="/usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js"
  if [[ -f "$libjs" ]]; then
    if ! grep -q 'orig_cmd(); return;' "$libjs"; then
      cp -a "$libjs" "${libjs}.bak-mc" 2>/dev/null || true
      sed -i "s/checked_command: function (orig_cmd) {/checked_command: function (orig_cmd) { orig_cmd(); return;/" \
        "$libjs"
      mc_say "Patched subscription nag in proxmoxlib.js"
    else
      mc_say "Subscription nag already patched"
    fi
    systemctl restart pveproxy.service 2>/dev/null || true
  else
    mc_say "proxmoxlib.js not found — skip nag patch"
  fi

  cat > /etc/apt/apt.conf.d/86no-nag-popup <<'EOF'
DPkg::Post-Invoke { "f=/usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js; if [ -f $f ] && ! grep -q 'orig_cmd(); return;' $f; then sed -i 's/checked_command: function (orig_cmd) {/checked_command: function (orig_cmd) { orig_cmd(); return;/' $f && systemctl restart pveproxy.service; fi"; };
EOF
  mc_say "Installed APT hook /etc/apt/apt.conf.d/86no-nag-popup"

  if [[ "${SKIP_PVE_APT_UPDATE:-0}" == "1" ]]; then
    mc_say "Skipping apt update (SKIP_PVE_APT_UPDATE=1)"
    return 0
  fi

  mc_say "Refreshing APT indexes (no-subscription)"
  if ! apt-get update; then
    mc_say "apt-get update reported errors — check /etc/apt/sources.list.d/ (enterprise still enabled?)"
    return 0
  fi
  mc_say "APT update OK"

  if [[ "${SKIP_PVE_UPGRADE:-0}" == "1" ]]; then
    mc_say "Skipping apt dist-upgrade (SKIP_PVE_UPGRADE=1)"
    return 0
  fi

  mc_say "Upgrading Proxmox host packages (apt-get dist-upgrade) — this can take several minutes"
  DEBIAN_FRONTEND=noninteractive apt-get -y dist-upgrade \
    || mc_say "dist-upgrade reported errors — review apt output before continuing"
  mc_say "Host upgrade finished — reboot the node later if a new kernel was installed (guests can be created first)"
}

mc_ensure_proxmox_api_token() {
  # Create hass@pve!missioncontrol (PVEVMUser) if PROXMOX_TOKEN_SECRET is unset.
  # Exports PROXMOX_TOKEN_ID and PROXMOX_TOKEN_SECRET.
  local user="${PROXMOX_TOKEN_USER:-hass@pve}"
  local token_name="${PROXMOX_TOKEN_NAME:-missioncontrol}"
  local full_id="${user}!${token_name}"

  if [[ -n "${PROXMOX_TOKEN_SECRET:-}" ]]; then
    PROXMOX_TOKEN_ID="${PROXMOX_TOKEN_ID:-$full_id}"
    export PROXMOX_TOKEN_ID PROXMOX_TOKEN_SECRET
    mc_say "Using provided Proxmox API token ${PROXMOX_TOKEN_ID}"
    return 0
  fi

  if ! command -v pveum >/dev/null 2>&1; then
    mc_say "pveum not found — leaving Proxmox token placeholder"
    PROXMOX_TOKEN_ID="${PROXMOX_TOKEN_ID:-$full_id}"
    PROXMOX_TOKEN_SECRET="${PROXMOX_TOKEN_SECRET:-}"
    export PROXMOX_TOKEN_ID PROXMOX_TOKEN_SECRET
    return 0
  fi

  mc_say "Ensuring Proxmox API user/token ${full_id}"
  pveum user add "$user" --comment "Mission Control / Home Assistant" 2>/dev/null || true
  pveum aclmod / -user "$user" -role PVEVMUser 2>/dev/null || true

  # Remove existing token so we can capture a fresh secret (venue reinstall / redeploy).
  pveum user token remove "$user" "$token_name" 2>/dev/null || true

  local raw secret
  raw="$(pveum user token add "$user" "$token_name" --privsep 0 --output-format json 2>/dev/null || true)"
  if [[ -z "$raw" ]]; then
    raw="$(pveum user token add "$user" "$token_name" --privsep 0 2>&1 || true)"
  fi
  secret="$(python3 -c "
import json, re, sys
raw = sys.stdin.read()
secret = ''
try:
    data = json.loads(raw)
    if isinstance(data, dict):
        secret = data.get('value') or data.get('token') or ''
        if not secret and isinstance(data.get('data'), dict):
            secret = data['data'].get('value') or data['data'].get('token') or ''
except Exception:
    pass
if not secret:
    m = re.search(r'(?:value|token)\s*[|=:]\s*([0-9a-fA-F-]{36})', raw)
    if m:
        secret = m.group(1)
    else:
        m = re.search(r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})', raw)
        if m:
            secret = m.group(1)
print(secret)
" <<<"$raw")"

  if [[ -z "$secret" ]]; then
    mc_say "Could not parse Proxmox token secret — set PROXMOX_TOKEN_SECRET manually"
    PROXMOX_TOKEN_ID="${PROXMOX_TOKEN_ID:-$full_id}"
    PROXMOX_TOKEN_SECRET=""
  else
    PROXMOX_TOKEN_ID="$full_id"
    PROXMOX_TOKEN_SECRET="$secret"
    mc_say "Created Proxmox API token ${PROXMOX_TOKEN_ID}"
  fi
  export PROXMOX_TOKEN_ID PROXMOX_TOKEN_SECRET
}

mc_prompt_central_urls() {
  # Prompt once when Central primary was not passed via env (venue operators).
  # Secondary may be empty (no LAN mirror) — never force 192.168.1.234.
  if [[ "${SKIP_CENTRAL_PROMPT:-0}" == "1" ]]; then
    CENTRAL_PRIMARY="${CENTRAL_PRIMARY:-https://your-cloud-player-api.example.com}"
    CENTRAL_SECONDARY="${CENTRAL_SECONDARY-}"
    export CENTRAL_PRIMARY CENTRAL_SECONDARY
    return 0
  fi
  if [[ -n "${CENTRAL_PRIMARY:-}" ]]; then
    # Primary from env; honor secondary as-is (including intentionally empty).
    CENTRAL_SECONDARY="${CENTRAL_SECONDARY-}"
    export CENTRAL_PRIMARY CENTRAL_SECONDARY
    return 0
  fi
  echo "" >&2
  echo "Central Server URLs (Registration pushes these to MCS on every HA start)." >&2
  echo "Secondary is optional — Enter skips (leave empty when there is no LAN mirror)." >&2
  read -r -p "  Central primary URL: " CENTRAL_PRIMARY </dev/tty || true
  read -r -p "  Central secondary URL (LAN mirror, or Enter to skip): " CENTRAL_SECONDARY </dev/tty || true
  CENTRAL_PRIMARY="${CENTRAL_PRIMARY:-https://your-cloud-player-api.example.com}"
  # Trim; keep empty when operator skips — do not substitute a dead default.
  CENTRAL_SECONDARY="$(echo -n "${CENTRAL_SECONDARY:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  export CENTRAL_PRIMARY CENTRAL_SECONDARY
  mc_say "Central primary=${CENTRAL_PRIMARY}"
  mc_say "Central secondary=${CENTRAL_SECONDARY:-"(empty)"}"
}

mc_ha_force_cc_reseed() {
  # Stop HA, drop the core_configurator config entry so YAML+secrets re-import, start HA.
  local ha_ip="$1"
  mc_say "Force-reseeding Core Configurator from secrets.yaml"
  mc_ha_ssh "$ha_ip" "ha core stop" || true
  sleep 3
  local tmp
  tmp="$(mktemp /tmp/mc-cc-entries.XXXXXX.json)"
  if scp -i "$MC_HA_KEY" \
    -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile=/root/.ssh/mc-ha-known_hosts \
    "root@${ha_ip}:/config/.storage/core.config_entries" \
    "$tmp" 2>/dev/null; then
    python3 - "$tmp" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
entries = data.get("data", {}).get("entries") or []
kept = [e for e in entries if e.get("domain") != "core_configurator"]
removed = len(entries) - len(kept)
data.setdefault("data", {})["entries"] = kept
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(f"removed {removed} core_configurator entr(y/ies)", flush=True)
PY
    scp -i "$MC_HA_KEY" \
      -o StrictHostKeyChecking=accept-new \
      -o UserKnownHostsFile=/root/.ssh/mc-ha-known_hosts \
      "$tmp" \
      "root@${ha_ip}:/config/.storage/core.config_entries"
  else
    mc_say "No core.config_entries yet — first boot will import from YAML"
  fi
  rm -f "$tmp"
  mc_ha_ssh "$ha_ip" "ha core start" || mc_ha_ssh "$ha_ip" "ha core restart" || true
}

mc_check_offline_prereqs() {
  # Warn (or die) when CT template / HAOS image cannot be downloaded offline.
  local template_storage="${1:-${TEMPLATE_STORAGE:-local}}"
  local template_prefix="${2:-${TEMPLATE:-ubuntu-24.04-standard}}"
  local have_tmpl=0 have_net=0

  if command -v pveam >/dev/null 2>&1; then
    if pveam list "$template_storage" 2>/dev/null | awk 'NR>1 {print $1}' | grep -Fq "$template_prefix"; then
      have_tmpl=1
    fi
  fi
  if curl -fsI --connect-timeout 3 --max-time 5 https://download.proxmox.com >/dev/null 2>&1 \
    || curl -fsI --connect-timeout 3 --max-time 5 https://github.com >/dev/null 2>&1; then
    have_net=1
  fi

  if [[ "$have_tmpl" -eq 1 ]]; then
    mc_say "LXC template matching '${template_prefix}' found on ${template_storage}"
    return 0
  fi

  if [[ "$have_net" -eq 1 ]]; then
    mc_say "No local '${template_prefix}' template yet — installer will download it (internet OK)"
    return 0
  fi

  cat <<EOF >&2

══════════════════════════════════════════════════════════════════════════════
 OFFLINE INSTALL — Linux CT template required
══════════════════════════════════════════════════════════════════════════════

This host has no internet and no matching LXC template on '${template_storage}'.

Mission Control companion containers need an Ubuntu 24.04 template, e.g.:
  ${template_prefix}_*_amd64.tar.zst

Before re-running this installer (on a machine that CAN reach the internet, or
from USB):

  1. Download the template on any Proxmox node with network:
       pveam update
       pveam available --section system | grep ${template_prefix}
       pveam download ${template_storage} <filename>

  2. Or copy a .tar.zst into:
       /var/lib/vz/template/cache/
     then confirm with:  pveam list ${template_storage}

Optional — Home Assistant OS image if HAOS download will also fail:
  Place haos_ova-*.qcow2.xz on this host and run with:
    HAOS_IMAGE=/path/to/haos_ova-XX.qcow2.xz bash …/install-mission-control.sh

══════════════════════════════════════════════════════════════════════════════

EOF
  mc_die "Offline install needs a Linux CT template on ${template_storage} (see above)"
}

mc_ha_apply_alleycat_theme() {
  # Persist Alleycat as the default light + dark theme (frontend_theme storage).
  local ha_ip="$1"
  mc_say "Setting default theme to Alleycat"
  local tmp
  tmp="$(mktemp /tmp/mc-frontend-theme.XXXXXX.json)"
  cat >"$tmp" <<'JSON'
{
  "version": 1,
  "minor_version": 1,
  "key": "frontend_theme",
  "data": {
    "frontend_default_theme": "Alleycat",
    "frontend_default_dark_theme": "Alleycat"
  }
}
JSON
  scp -i "$MC_HA_KEY" \
    -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile=/root/.ssh/mc-ha-known_hosts \
    "$tmp" \
    "root@${ha_ip}:/config/.storage/frontend_theme"
  rm -f "$tmp"
  # Also fire the service once HA is up (covers users who already picked "Backend-selected")
  mc_ha_ssh "$ha_ip" bash -s <<'THEME' || true
set +e
HDR=""
if [ -n "${SUPERVISOR_TOKEN:-}" ]; then
  HDR="Authorization: Bearer ${SUPERVISOR_TOKEN}"
fi
if [ -n "$HDR" ]; then
  curl -fsS -X POST -H "$HDR" -H "Content-Type: application/json" \
    http://supervisor/core/api/services/frontend/set_theme \
    -d '{"name":"Alleycat","name_dark":"Alleycat"}' >/dev/null 2>&1 || true
fi
THEME
}

mc_ha_bootstrap_hacs() {
  # Install HACS custom component (needs GitHub download). Operator still authorizes
  # once in the UI. custom-sidebar/card-mod are vendored separately so Mission Control
  # rename works even if this step fails offline.
  local ha_ip="$1"
  mc_say "Installing HACS (best effort — needs HA internet + one-time GitHub authorize)"
  mc_ha_ssh "$ha_ip" bash -s <<'HACS' || mc_say "HACS download skipped/failed — vendored sidebar still provides Mission Control title"
set -euo pipefail
if [ -d /config/custom_components/hacs ]; then
  echo "HACS already present"
  exit 0
fi
mkdir -p /config/custom_components
cd /tmp
rm -f hacs.zip
if command -v wget >/dev/null 2>&1; then
  wget -q -O hacs.zip "https://github.com/hacs/integration/releases/latest/download/hacs.zip" || exit 1
elif command -v curl >/dev/null 2>&1; then
  curl -fsSL -o hacs.zip "https://github.com/hacs/integration/releases/latest/download/hacs.zip" || exit 1
else
  echo "No wget/curl in HA SSH — cannot fetch HACS"
  exit 1
fi
rm -rf /config/custom_components/hacs
mkdir -p /config/custom_components/hacs
unzip -qo hacs.zip -d /config/custom_components/hacs
rm -f hacs.zip
echo "HACS unpacked — add the HACS integration in Settings → Devices after restart (GitHub device code once)"
HACS
}

mc_ha_bootstrap_mqtt() {
  # Install Mosquitto, set venue login, create/accept MQTT config entry via Supervisor API.
  local ha_ip="$1"
  mc_say "Bootstrapping Mosquitto + MQTT integration"
  mc_ha_ssh "$ha_ip" bash -s <<'MQTTBOOT' || mc_say "MQTT bootstrap incomplete — finish in UI if needed"
set -euo pipefail
ha addons install core_mosquitto 2>/dev/null || true
ha addons options core_mosquitto <<'EOF' || true
logins:
  - username: alleycatTV
    password: alleycat
EOF
ha addons start core_mosquitto 2>/dev/null || true

auth_hdr() {
  if [ -n "${SUPERVISOR_TOKEN:-}" ]; then
    printf 'Authorization: Bearer %s' "${SUPERVISOR_TOKEN}"
    return 0
  fi
  local tok=""
  tok="$(cat /root/.hassio/supervisor_token 2>/dev/null || true)"
  if [ -z "$tok" ] && [ -f /etc/hassio.json ]; then
    tok="$(python3 -c "import json;print(json.load(open('/etc/hassio.json')).get('supervisor_token',''))" 2>/dev/null || true)"
  fi
  printf 'Authorization: Bearer %s' "${tok}"
}

HDR="$(auth_hdr)"
API="http://supervisor/core/api"

if curl -fsS -H "$HDR" "${API}/config/config_entries/entry" 2>/dev/null \
  | grep -q '"domain":"mqtt"'; then
  echo "MQTT config entry already present"
  exit 0
fi

sleep 5

# Prefer confirming an in-progress / discovery flow for mqtt
DISC="$(curl -fsS -H "$HDR" "${API}/config/config_entries/flow" 2>/dev/null || true)"
FLOW_ID="$(python3 -c "
import json,sys
raw=sys.stdin.read()
try:
    data=json.loads(raw)
except Exception:
    data=[]
cands=[]
if isinstance(data, list):
    for f in data:
        if isinstance(f, dict) and f.get('handler')=='mqtt':
            cands.append(f.get('flow_id') or '')
print(cands[0] if cands else '')
" <<<"$DISC")"

if [ -n "$FLOW_ID" ]; then
  curl -fsS -X POST -H "$HDR" -H "Content-Type: application/json" \
    "${API}/config/config_entries/flow/${FLOW_ID}" \
    -d '{}' >/dev/null 2>&1 || true
fi

INIT="$(curl -fsS -X POST -H "$HDR" -H "Content-Type: application/json" \
  "${API}/config/config_entries/flow" \
  -d '{"handler":"mqtt","show_advanced_options":false}' 2>/dev/null || true)"
FLOW_ID="$(python3 -c "
import json,sys
try:
    d=json.loads(sys.stdin.read())
except Exception:
    d={}
print(d.get('flow_id') or '')
" <<<"$INIT")"

if [ -n "$FLOW_ID" ]; then
  curl -fsS -X POST -H "$HDR" -H "Content-Type: application/json" \
    "${API}/config/config_entries/flow/${FLOW_ID}" \
    -d '{"broker":"core-mosquitto","port":1883,"username":"alleycatTV","password":"alleycat"}' \
    >/dev/null 2>&1 \
  || curl -fsS -X POST -H "$HDR" -H "Content-Type: application/json" \
    "${API}/config/config_entries/flow/${FLOW_ID}" \
    -d '{}' >/dev/null 2>&1 \
  || true
fi

if curl -fsS -H "$HDR" "${API}/config/config_entries/entry" 2>/dev/null \
  | grep -q '"domain":"mqtt"'; then
  echo "MQTT config entry created"
else
  echo "MQTT entry not confirmed — operator may need Add Integration → MQTT once"
  exit 1
fi
MQTTBOOT
}
