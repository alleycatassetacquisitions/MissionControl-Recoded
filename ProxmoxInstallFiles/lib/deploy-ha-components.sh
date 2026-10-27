#!/usr/bin/env bash
# Deploy Mission Control custom_components + www (+ themes) into HA /config.
# Usage: bash deploy-ha-components.sh <ha_ip> <src_root>
# Requires MC_HA_KEY deploy key (default /root/.ssh/mc-ha).

set -euo pipefail

HA_IP="${1:?HA IP required}"
SRC="${2:?src root required}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=mc-install-common.sh
source "${SCRIPT_DIR}/mc-install-common.sh"

mc_ensure_ha_keypair
mc_say "Deploying HA components to ${HA_IP}"

mc_ha_ssh "$HA_IP" "mkdir -p /config/custom_components /config/www /config/themes"

deploy_pair() {
  local cc_src="$1" www_src="${2:-}"
  local name
  name="$(basename "$cc_src")"
  if [[ -d "$cc_src" ]]; then
    mc_ha_rsync_tree "$HA_IP" "$cc_src" "custom_components/${name}"
  fi
  if [[ -n "$www_src" && -d "$www_src" ]]; then
    local wname
    wname="$(basename "$www_src")"
    mc_ha_rsync_tree "$HA_IP" "$www_src" "www/${wname}"
  fi
}

deploy_pair \
  "$SRC/Libraries/Shared_HA_Helpers/HA_Component/custom_components/shared_libraries" \
  "$SRC/Libraries/Shared_HA_Helpers/HA_Component/www/shared_libraries"

deploy_pair \
  "$SRC/Apps/Core_Configurator/HA_Component/custom_components/core_configurator" \
  "$SRC/Apps/Core_Configurator/HA_Component/www/core_configurator"

deploy_pair \
  "$SRC/Apps/Registration/HA_Component/custom_components/registration" \
  "$SRC/Apps/Registration/HA_Component/www/registration"

deploy_pair \
  "$SRC/Apps/Digital_Node_Nexus/HA_Component/custom_components/digital_node_nexus" \
  "$SRC/Apps/Digital_Node_Nexus/HA_Component/www/digital_node_nexus"

deploy_pair \
  "$SRC/Apps/AlleycatTV/HA_Component/custom_components/alleycattv" \
  "$SRC/Apps/AlleycatTV/HA_Component/www/alleycattv"

deploy_pair \
  "$SRC/Apps/Broadcast_Group_Controller/HA_Component/custom_components/broadcast_group_controller" \
  "$SRC/Apps/Broadcast_Group_Controller/HA_Component/www/broadcast_group_controller"

deploy_pair \
  "$SRC/Apps/Galactic_Bounty_Network/HA_Component/custom_components/gbn" \
  "$SRC/Apps/Galactic_Bounty_Network/HA_Component/www/gbn"

deploy_pair \
  "$SRC/Apps/Bug_Buster/HA_Component/custom_components/bug_buster" \
  "$SRC/Apps/Bug_Buster/HA_Component/www/bug_buster"

deploy_pair \
  "$SRC/Apps/Game_Master/HA_Component/custom_components/game_master" \
  "$SRC/Apps/Game_Master/HA_Component/www/game_master"

deploy_pair \
  "$SRC/Apps/Net_Time/HA_Component/custom_components/net_time" \
  "$SRC/Apps/Net_Time/HA_Component/www/net_time"

if [[ -d "$SRC/HomeAssist/themes" ]]; then
  mc_ha_rsync_tree "$HA_IP" "$SRC/HomeAssist/themes" "themes"
fi
if [[ -f "$SRC/HomeAssist/www/alleycat-scanlines.js" ]]; then
  scp -i "$MC_HA_KEY" \
    -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile=/root/.ssh/mc-ha-known_hosts \
    "$SRC/HomeAssist/www/alleycat-scanlines.js" \
    "root@${HA_IP}:/config/www/"
fi
if [[ -f "$SRC/HomeAssist/www/custom-sidebar-config.yaml" ]]; then
  scp -i "$MC_HA_KEY" \
    -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile=/root/.ssh/mc-ha-known_hosts \
    "$SRC/HomeAssist/www/custom-sidebar-config.yaml" \
    "root@${HA_IP}:/config/www/"
fi
# Vendored custom-sidebar + card-mod (Mission Control title + Alleycat card-mod)
if [[ -d "$SRC/HomeAssist/www/mc-shell" ]]; then
  mc_ha_rsync_tree "$HA_IP" "$SRC/HomeAssist/www/mc-shell" "www/mc-shell"
elif [[ -f "${SCRIPT_DIR}/fetch-ha-shell.sh" ]]; then
  mc_say "mc-shell missing — fetching custom-sidebar + card-mod"
  bash "${SCRIPT_DIR}/fetch-ha-shell.sh" "${SRC}/HomeAssist/www/mc-shell" \
    && mc_ha_rsync_tree "$HA_IP" "$SRC/HomeAssist/www/mc-shell" "www/mc-shell" \
    || mc_say "Could not fetch mc-shell — sidebar may stay named Home Assistant until plugins are present"
fi

mc_say "HA component files deployed (core restart is done by the orchestrator)"
