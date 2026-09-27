#!/usr/bin/env bash
##############################################################################
# provision-lxc.sh â€” Create the AlleycatTV Proxmox LXC container
#
# Run this ON the Proxmox host (not inside the container).
# Adjust the variables below before running.
#
# Usage:
#   chmod +x provision-lxc.sh
#   ./provision-lxc.sh
##############################################################################
set -euo pipefail

# â”€â”€ Configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CTID=200                        # Container ID (pick a free one)
HOSTNAME="alleycattv"
CORES=2
RAM_MB=2048
DISK_GB=60                      # Adjust upward for larger media libraries
STORAGE="local-lvm"             # Proxmox storage pool
BRIDGE="vmbr0"                  # Network bridge
IP="192.168.1.100/24"           # Static IP for the container
GW="192.168.1.1"                # Gateway
TEMPLATE="local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst"

# â”€â”€ Download Ubuntu 22.04 template if missing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if ! pveam list local | grep -q "ubuntu-22.04"; then
    echo "Downloading Ubuntu 22.04 LXC template..."
    pveam update
    pveam download local ubuntu-22.04-standard_22.04-1_amd64.tar.zst
fi

# â”€â”€ Create container â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "Creating LXC container $CTID ($HOSTNAME)..."
pct create "$CTID" "$TEMPLATE" \
    --hostname "$HOSTNAME" \
    --cores "$CORES" \
    --memory "$RAM_MB" \
    --rootfs "$STORAGE:$DISK_GB" \
    --net0 "name=eth0,bridge=$BRIDGE,ip=$IP,gw=$GW" \
    --ostype ubuntu \
    --unprivileged 1 \
    --features nesting=1 \
    --start 1

echo "Waiting for container to start..."
sleep 5

# â”€â”€ Copy install script into container and run it â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
echo "Copying install-server.sh to container..."
pct push "$CTID" "$(dirname "$0")/install-server.sh" /root/install-server.sh
pct exec "$CTID" -- bash /root/install-server.sh

echo ""
echo "AlleycatTV server provisioned at http://${IP%/*}"
echo "  API:   http://${IP%/*}/api/"
echo "  Media: http://${IP%/*}/media/"
