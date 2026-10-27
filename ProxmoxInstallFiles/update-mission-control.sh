#!/usr/bin/env bash
# Check GitHub (or a local BUNDLE) for venue updates and apply changed components.
#
# Run on the Proxmox HOST after a venue install:
#   bash /root/mission-control-src/ProxmoxInstallFiles/update-mission-control.sh --check
#   bash /root/mission-control-src/ProxmoxInstallFiles/update-mission-control.sh --yes
#
# Env:
#   BUNDLE=/path/to/extracted-or-tarball   offline update
#   MC_SRC_ROOT=/root/mission-control-src
#   MC_STATE_FILE=/root/mission-control-install-state.json
#   ONLY=mcs,net_time,ha
#   GH_TOKEN=…  RELEASE_URL=…

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/mc-install-common.sh
source "${SCRIPT_DIR}/lib/mc-install-common.sh"

CHECK_ONLY=0
APPLY_YES=0
JSON_OUT=0
ONLY="${ONLY:-}"
BUNDLE="${BUNDLE:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK_ONLY=1; shift ;;
    --yes) APPLY_YES=1; shift ;;
    --json) JSON_OUT=1; shift ;;
    --only=*) ONLY="${1#*=}"; shift ;;
    --only) ONLY="${2:-}"; shift 2 ;;
    *) mc_die "Unknown arg: $1" ;;
  esac
done

mc_require_proxmox
mc_state_init_empty
[[ -f "$MC_STATE_FILE" ]] || mc_die "No install state at $MC_STATE_FILE — run install-mission-control.sh first"

WORK="$(mktemp -d /tmp/mc-update.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

resolve_bundle() {
  if [[ -n "$BUNDLE" ]]; then
    if [[ -f "$BUNDLE" && "$BUNDLE" == *.tar.gz ]]; then
      mkdir -p "$WORK/extract"
      tar -xzf "$BUNDLE" -C "$WORK/extract"
      BUNDLE="$(find "$WORK/extract" -maxdepth 3 -name manifest.json | head -1 | xargs -r dirname)"
    fi
    [[ -d "$BUNDLE" ]] || mc_die "BUNDLE not found: $BUNDLE"
    [[ -f "$BUNDLE/manifest.json" ]] || mc_die "manifest.json missing in BUNDLE"
    printf '%s' "$BUNDLE"
    return
  fi
  mc_fetch_latest_release "$WORK"
}

NEW_ROOT="$(resolve_bundle)"
REMOTE_MANIFEST="$NEW_ROOT/manifest.json"
[[ -f "$REMOTE_MANIFEST" ]] || mc_die "No manifest in $NEW_ROOT"

python3 - "$MC_STATE_FILE" "$REMOTE_MANIFEST" "$ONLY" "$CHECK_ONLY" "$JSON_OUT" "$APPLY_YES" "$NEW_ROOT" "$SCRIPT_DIR" <<'PY'
import json, os, subprocess, sys

state_path, remote_path, only, check_only, json_out, apply_yes, new_root, script_dir = sys.argv[1:9]
check_only = check_only == "1"
json_out = json_out == "1"
apply_yes = apply_yes == "1"
only_set = {x.strip() for x in only.split(",") if x.strip()} if only else set()

with open(state_path, encoding="utf-8") as f:
    state = json.load(f)
with open(remote_path, encoding="utf-8") as f:
    remote = json.load(f)

installed = state.get("components") or {}
remote_comps = remote.get("components") or {}
changed = []
for key, meta in remote_comps.items():
    if only_set and key not in only_set:
        continue
    want = (meta or {}).get("digest") or ""
    have = (installed.get(key) or {}).get("digest") or ""
    if want and want != have:
        changed.append(key)

result = {
    "status": "update_available" if changed else "up_to_date",
    "installed_release": state.get("release"),
    "latest_release": remote.get("release"),
    "latest_published_at": remote.get("created_at"),
    "last_updated_at": state.get("last_updated_at"),
    "commit": remote.get("commit"),
    "summary": remote.get("summary") or remote.get("release") or "",
    "changed_components": changed,
}

if check_only or not changed:
    if json_out:
        print(json.dumps(result))
    else:
        print(f"Status: {result['status']}")
        print(f"Installed: {result['installed_release']}")
        print(f"Latest:    {result['latest_release']}")
        print(f"Last updated: {result.get('last_updated_at') or 'unknown'}")
        if changed:
            print("Changed:", ", ".join(changed))
    sys.exit(1 if changed else 0)

if not apply_yes and not json_out:
    print("Updates available for:", ", ".join(changed))
    print("Re-run with --yes to apply.")
    sys.exit(1)

# Apply
push = os.path.join(script_dir, "lib", "push-server-component.sh")
services = state.get("services") or {}

def run(cmd, env=None):
    print("==>", " ".join(cmd), file=sys.stderr)
    subprocess.check_call(cmd, env=env)

applied = []
errors = []

# Component → CT push map
MAP = {
    "mcs": ("mcs", "/opt/mcs", "Apps/Master_Control_Server/Server_Component"),
    "alleycattv": (
        "alleycattv-server",
        "/opt/alleycattv/server",
        "Apps/AlleycatTV/Server_Component",
    ),
    "gbn": ("gbn", "/opt/gbn", "Apps/Galactic_Bounty_Network/Server_Component"),
    "net_time": ("net-time", "/opt/net_time", "Apps/Net_Time/Server_Component"),
}

for key in changed:
    if key in MAP:
        unit, dest, rel = MAP[key]
        ctid = str((services.get(key) or {}).get("ctid") or "")
        if not ctid:
            errors.append(f"{key}: missing ctid in state")
            continue
        src = os.path.join(new_root, rel)
        env = os.environ.copy()
        env.update({"CTID": ctid, "UNIT": unit, "DEST": dest, "SRC": src})
        try:
            run(["bash", push], env=env)
            applied.append(key)
        except subprocess.CalledProcessError as exc:
            errors.append(f"{key}: push failed ({exc})")
        # Net Time host agent refresh
        if key == "net_time":
            agent_src = os.path.join(new_root, "Apps/Net_Time/Server_Component/host_clock_agent.py")
            if os.path.isfile(agent_src):
                run(["install", "-m", "0755", agent_src, "/usr/local/sbin/net-time-host-clock"])
                run(["systemctl", "restart", "net-time-host-clock"])
    elif key == "ha":
        ha_ip = state.get("ha_ip") or ""
        if not ha_ip:
            errors.append("ha: missing ha_ip in state")
            continue
        deploy = os.path.join(script_dir, "lib", "deploy-ha-components.sh")
        if os.path.isfile(deploy):
            try:
                run(["bash", deploy, ha_ip, new_root])
                applied.append("ha")
            except subprocess.CalledProcessError as exc:
                errors.append(f"ha: deploy failed ({exc})")
        else:
            errors.append("ha: deploy-ha-components.sh missing")
    elif key == "scripts":
        # Refresh staged scripts + venue update agent
        agent_src = os.path.join(new_root, "ProxmoxInstallFiles/venue_update_agent.py")
        if os.path.isfile(agent_src):
            run(["install", "-m", "0755", agent_src, "/usr/local/sbin/mc-venue-update"])
            run(["systemctl", "restart", "mc-venue-update"])
        applied.append("scripts")

# Update staged source tree
import shutil
src_root = os.environ.get("MC_SRC_ROOT", "/root/mission-control-src")
if os.path.isdir(new_root) and os.path.abspath(new_root) != os.path.abspath(src_root):
    os.makedirs(src_root, exist_ok=True)
    # Copy over key trees
    for name in ("Apps", "Libraries", "HomeAssist", "ProxmoxInstallFiles", "manifest.json"):
        s = os.path.join(new_root, name)
        d = os.path.join(src_root, name)
        if not os.path.exists(s):
            continue
        if os.path.isdir(s):
            if os.path.isdir(d):
                shutil.rmtree(d)
            shutil.copytree(s, d, ignore=shutil.ignore_patterns(".venv", "__pycache__", "node_modules", ".git"))
        else:
            shutil.copy2(s, d)

from datetime import datetime, timezone
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
state["release"] = remote.get("release")
state["commit"] = remote.get("commit")
state["last_updated_at"] = now
comps = state.setdefault("components", {})
for key in applied:
    if key in remote_comps:
        comps[key] = {"digest": remote_comps[key].get("digest"), "updated_at": now}

with open(state_path, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2)
    f.write("\n")

result["status"] = "ok" if not errors else "error"
result["applied"] = applied
result["errors"] = errors
result["last_updated_at"] = now

if json_out:
    print(json.dumps(result))
else:
    print("Applied:", ", ".join(applied) or "(none)")
    if errors:
        print("Errors:", "; ".join(errors))
sys.exit(0 if not errors else 2)
PY
