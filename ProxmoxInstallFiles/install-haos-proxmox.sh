#!/usr/bin/env bash
# Create a Home Assistant OS VM on this Proxmox node.
#
# Run on the Proxmox HOST shell (the node, not a guest). Matches
# Docs/Home Assistant Config Steps.md
#
# Phone walkthrough: open the node Shell in the Proxmox UI, paste:
#   bash install-haos-proxmox.sh
#
# Optional environment overrides:
#   VMID=101 STORAGE=local-lvm BRIDGE=vmbr0 START_VM=1 HAOS_VERSION=18.3
# VMID is optional. If omitted (or already in use), the next free ID is used.

set -euo pipefail

REQUESTED_VMID="${VMID:-}"
VM_NAME="${VM_NAME:-Home-Assistant}"
STORAGE="${STORAGE:-local-lvm}"
BRIDGE="${BRIDGE:-vmbr0}"
CORES="${CORES:-4}"
SOCKETS="${SOCKETS:-1}"
CPU_TYPE="${CPU_TYPE:-x86-64-v2-AES}"
MEMORY_MB="${MEMORY_MB:-8192}"
DISK_SIZE="${DISK_SIZE:-32G}"
START_VM="${START_VM:-1}"
HAOS_VERSION="${HAOS_VERSION:-}"
SKIP_CONFIRM="${SKIP_CONFIRM:-0}"

IMAGE_REPO="https://github.com/home-assistant/operating-system/releases/download"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

require_proxmox() {
  command -v qm >/dev/null 2>&1 || die "qm not found. Run this on the Proxmox node shell, not inside a VM."
  command -v pvesm >/dev/null 2>&1 || die "pvesm not found. This does not look like a Proxmox host."
}

vmid_in_use() {
  qm status "$1" >/dev/null 2>&1
}

next_free_vmid() {
  local id="$1"
  while vmid_in_use "$id"; do
    id=$((id + 1))
    if [[ "$id" -gt 999999999 ]]; then
      die "Could not find a free VM ID."
    fi
  done
  printf '%s' "$id"
}

cluster_next_vmid() {
  local id=""
  if command -v pvesh >/dev/null 2>&1; then
    id="$(pvesh get /cluster/nextid 2>/dev/null | tr -d '[:space:]' || true)"
  fi
  if [[ "$id" =~ ^[0-9]+$ ]] && ! vmid_in_use "$id"; then
    printf '%s' "$id"
    return 0
  fi
  next_free_vmid 100
}

choose_vmid() {
  if [[ -n "$REQUESTED_VMID" ]]; then
    if vmid_in_use "$REQUESTED_VMID"; then
      printf '\n==> VMID %s is already in use; choosing the next free ID\n' "$REQUESTED_VMID" >&2
    else
      printf '%s' "$REQUESTED_VMID"
      return 0
    fi
  fi
  cluster_next_vmid
}

storage_exists() {
  pvesm status --storage "$1" >/dev/null 2>&1
}

fetch_haos_version() {
  local ver=""
  ver="$(curl -fsSL https://version.home-assistant.io/stable.json 2>/dev/null \
    | grep -o '"ova"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4 || true)"
  if [[ -z "$ver" ]]; then
    ver="$(curl -fsSL https://api.github.com/repos/home-assistant/operating-system/releases/latest 2>/dev/null \
      | grep -o '"tag_name": "[^"]*"' | head -1 | cut -d'"' -f4 || true)"
  fi
  [[ -n "$ver" ]] || die "Could not look up the current Home Assistant OS version. Set HAOS_VERSION and retry."
  printf '%s' "$ver"
}

imported_disk_ref() {
  local output="$1"
  local ref=""
  ref="$(printf '%s\n' "$output" | tr -d '\r' \
    | sed -n "s/.*[Ss]uccessfully imported disk '\([^']\+\)'.*/\1/p" \
    | tail -1 || true)"
  if [[ -z "$ref" ]]; then
    ref="$(pvesm list "$STORAGE" | awk -v vmid="$VMID" 'NR > 1 && $NF == vmid { print $1 }' | sort | tail -1 || true)"
  fi
  # importdisk reports unused0:storage:volname; qm set --scsi0 wants storage:volname
  if [[ "$ref" == unused* ]]; then
    ref="${ref#*:}"
  fi
  printf '%s' "$ref"
}

require_proxmox
storage_exists "$STORAGE" || die "Storage '$STORAGE' was not found. Check Datacenter → Storage."

VMID="$(choose_vmid)"

if [[ -z "$HAOS_VERSION" ]]; then
  say "Looking up the current Home Assistant OS (KVM/Proxmox) image"
  HAOS_VERSION="$(fetch_haos_version)"
fi

ARCHIVE="haos_ova-${HAOS_VERSION}.qcow2.xz"
IMAGE="haos_ova-${HAOS_VERSION}.qcow2"
URL="${IMAGE_REPO}/${HAOS_VERSION}/${ARCHIVE}"

cat <<EOF

This will create a Home Assistant OS VM on this Proxmox node:

  VMID          $VMID
  Name          $VM_NAME
  HAOS          $HAOS_VERSION
  CPU           ${CORES} cores (${CPU_TYPE})
  Memory        ${MEMORY_MB} MiB
  Disk          ${DISK_SIZE} on ${STORAGE}
  Bridge        ${BRIDGE}
  BIOS          OVMF (UEFI), machine q35
  Start after   $([[ "$START_VM" == "1" ]] && echo yes || echo no)

EOF

if [[ "$SKIP_CONFIRM" != "1" ]]; then
  say "Starting in 5 seconds. Press Ctrl-C to cancel."
  sleep 5
fi

WORKDIR="$(mktemp -d /var/tmp/haos-install.XXXXXX 2>/dev/null || mktemp -d /tmp/haos-install.XXXXXX)"
cleanup() {
  local ec=$?
  if [[ "$ec" -eq 0 ]]; then
    rm -rf "$WORKDIR"
  else
    printf '\nLeft files in %s (delete them after you are done troubleshooting).\n' "$WORKDIR" >&2
  fi
}
trap cleanup EXIT
cd "$WORKDIR"

say "Downloading $URL"
# Official KVM/Proxmox image from https://www.home-assistant.io/installation/alternative
if command -v wget >/dev/null 2>&1; then
  wget -c --show-progress -O "$ARCHIVE" "$URL"
else
  curl -fL --retry 3 -o "$ARCHIVE" "$URL"
fi
[[ -s "$ARCHIVE" ]] || die "Download failed or the file is empty: $URL"

say "Extracting $ARCHIVE (this can take a minute)"
unxz -f "$ARCHIVE"
[[ -s "$IMAGE" ]] || die "Extracted image missing: $IMAGE"

say "Creating VM $VMID ($VM_NAME)"
qm create "$VMID" \
  --name "$VM_NAME" \
  --memory "$MEMORY_MB" \
  --cores "$CORES" \
  --sockets "$SOCKETS" \
  --cpu "$CPU_TYPE" \
  --machine q35 \
  --bios ovmf \
  --scsihw virtio-scsi-single \
  --net0 "virtio,bridge=${BRIDGE},firewall=1" \
  --ostype l26 \
  --onboot 1 \
  --agent 0 \
  --tablet 1 \
  --hotplug disk,network,usb

say "Importing $IMAGE into $STORAGE (this can take several minutes)"
IMPORT_CMD=(qm importdisk)
if qm disk import --help >/dev/null 2>&1; then
  IMPORT_CMD=(qm disk import)
fi

IMPORT_LOG="${WORKDIR}/import.log"
set +e
"${IMPORT_CMD[@]}" "$VMID" "$IMAGE" "$STORAGE" 2>&1 | tee "$IMPORT_LOG"
IMPORT_STATUS=${PIPESTATUS[0]}
set -e
[[ "$IMPORT_STATUS" -eq 0 ]] || die "Disk import failed. See ${IMPORT_LOG}."

DISK_REF="$(imported_disk_ref "$(cat "$IMPORT_LOG")")"
[[ -n "$DISK_REF" ]] || die "Imported the disk but could not find its storage reference."
say "Imported disk: $DISK_REF"

attach_scsi_disk() {
  if qm set "$VMID" --scsi0 "${DISK_REF},discard=on,iothread=1"; then
    return 0
  fi
  say "Retrying SCSI attach without iothread"
  qm set "$VMID" --scsi0 "${DISK_REF},discard=on"
}

attach_efi_disk() {
  # Schema name is pre-enrolled-keys (not pre-enroll-keys). Older PVE has neither.
  local attempts=(
    "${STORAGE}:1,efitype=4m,pre-enrolled-keys=0"
    "${STORAGE}:1,format=raw,efitype=4m,pre-enrolled-keys=0"
    "${STORAGE}:1,efitype=4m"
    "${STORAGE}:1,format=raw,efitype=4m"
    "${STORAGE}:1,format=raw"
    "${STORAGE}:1"
  )
  local spec
  for spec in "${attempts[@]}"; do
    say "Trying EFI disk ${spec}"
    if qm set "$VMID" --efidisk0 "$spec"; then
      return 0
    fi
  done
  die "Could not add an EFI disk. In the UI: Hardware → Add → EFI Disk, storage ${STORAGE}, uncheck Pre-Enroll keys."
}

say "Attaching the HAOS disk, EFI disk, and boot order"
attach_scsi_disk
attach_efi_disk
qm set "$VMID" --boot "order=scsi0"

if qm resize "$VMID" scsi0 "$DISK_SIZE"; then
  say "Disk size is $DISK_SIZE"
else
  say "Disk resize to $DISK_SIZE skipped (already that size, or storage does not allow it)"
fi

if [[ "$START_VM" == "1" ]]; then
  say "Starting $VM_NAME"
  qm start "$VMID"
fi

cat <<EOF

Done. VM $VMID ($VM_NAME) is ready.

Wait 2–5 minutes for Home Assistant OS to boot, then open:
  http://homeassistant.local
  http://homeassistant.local:8123

If those do not resolve, open the VM console in Proxmox and use the IP it prints,
or try http://homeassistant:8123

Onboarding: https://www.home-assistant.io/getting-started/onboarding/

EOF
