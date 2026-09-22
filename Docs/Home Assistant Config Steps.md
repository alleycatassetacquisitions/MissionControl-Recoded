# Home Assistant Config Steps

Required configuration for Home Assistant integration.

This assumes you are using **Proxmox**. Install **Home Assistant OS** as a virtual machine from the official KVM/Proxmox disk image. Do not install Home Assistant Container for Mission Control.

The installer script does the work shown in [Installing Home Assistant on Proxmox](https://youtu.be/CXBqeis7fgc) and uses the current image from [Home Assistant — Alternative installation](https://www.home-assistant.io/installation/alternative). The tables below are the Mission Control target (not the video’s minimums). The script applies them and picks the next free VM ID.

## Install

Run this on the **Proxmox node shell** (Datacenter → the host → **Shell**). Do not open a guest console.

1. Copy `Docs/install-haos-proxmox.sh` onto the Proxmox host as `/root/install-haos-proxmox.sh` (USB, SCP, or paste into `nano`).
2. In the node Shell:

```bash
bash /root/install-haos-proxmox.sh
```

3. Wait for `Done. VM … is ready.` First boot takes a few minutes.
4. On any computer on the same LAN, open [http://homeassistant.local](http://homeassistant.local) or [http://homeassistant.local:8123](http://homeassistant.local:8123).

If those do not resolve, open the VM console in Proxmox and use the IP it prints, or try [http://homeassistant:8123](http://homeassistant:8123). Continue with [onboarding](https://www.home-assistant.io/getting-started/onboarding/).

The script names the VM `Home-Assistant`, uses 4 cores, 8 GB RAM, 32 GB on `local-lvm`, and bridge `vmbr0`.

## Virtual machine resources

| Setting     | Value   |
| ----------- | ------- |
| CPU         | 4 cores |
| RAM         | 8 GB    |
| Swap memory | 4 GB    |
| Disk size   | 32 GB   |

Home Assistant’s published minimum is 2 vCPUs and 2 GB RAM. Mission Control uses the table above. Swap is managed inside Home Assistant OS after first boot; Proxmox does not set it.

## Proxmox hardware

| Device                  | Value                                              |
| ----------------------- | -------------------------------------------------- |
| Memory                  | 8.00 GiB                                           |
| Processors              | 4 (1 socket, 4 cores) `[x86-64-v2-AES]`            |
| BIOS                    | OVMF (UEFI)                                        |
| EFI                     | `efitype=4m`, Pre-Enroll keys **off**              |
| Display                 | Default                                            |
| Machine                 | q35                                                |
| SCSI Controller         | VirtIO SCSI single                                 |
| CD/DVD Drive (ide2)     | none, media=cdrom                                  |
| Hard Disk (scsi0)       | `local-lvm`, discard=on, iothread=1, size=32G      |
| Network Device (net0)   | virtio, bridge=`vmbr0`, firewall=1                 |
| EFI Disk                | `local-lvm`, efitype=4m, size=4M                   |

The MAC address and disk IDs (`vm-*-disk-*`) are generated per VM. Do not copy them from another machine.

## Proxmox VM options

Name the VM `Home-Assistant`.

| Option                         | Value                              |
| ------------------------------ | ---------------------------------- |
| Start at boot                  | Yes                                |
| Start/Shutdown order           | order=any                          |
| OS Type                        | Linux 7.x - 2.6 Kernel             |
| Boot Order                     | scsi0                              |
| Use tablet for pointer         | Yes                                |
| Hotplug                        | Disk, Network, USB                 |
| ACPI support                   | Yes                                |
| KVM hardware virtualization    | Yes                                |
| Freeze CPU at startup          | No                                 |
| Use local time for RTC         | Default (Enabled for Windows)      |
| RTC start date                 | now                                |
| QEMU Guest Agent               | Default (Disabled)                 |
| Protection                     | No                                 |
| Spice Enhancements             | none                               |
| VM State storage               | Automatic                          |
| AMD SEV                        | Default (Disabled)                 |
| Intel TDX                      | Default (Disabled)                 |

SMBIOS type1 UUID is generated per VM. Do not copy it from another machine.

## Enabling SSH for file transfers

SSH is how you copy Mission Control files onto the HA instance. Do this once after onboarding before deploying any integration.

### 1 — Enable Advanced Mode

SSH is hidden until Advanced Mode is on.

1. Click your username in the bottom-left of the HA sidebar.
2. Toggle **Advanced Mode** on.

### 2 — Install Terminal & SSH

1. **Settings → Apps → Install app**
2. Search for **Terminal & SSH** and install it.

### 3 — Generate an SSH key on your dev machine (Windows)

Run in PowerShell. Skip if you already have `~/.ssh/id_ed25519.pub`.

```powershell
ssh-keygen -t ed25519 -C "mission-control"
```

Press Enter three times to accept defaults (no passphrase). Then copy the public key to your clipboard:

```powershell
cat ~/.ssh/id_ed25519.pub | clip
```

### 4 — Configure the add-on

In the **Terminal & SSH** add-on:

1. Go to the **Options** tab.
2. Paste the clipboard contents into the **Authorized Keys** field and press Enter to create the chip. Confirm the full `ssh-ed25519 AAAA…` key is visible in the chip — not just a fingerprint.
3. Leave **Password** blank.
4. Click **Save** on the Options section.
5. Scroll to the **Network** section. Set the SSH port field to `22`. Click **Save**.
6. Go to the **Info** tab and click **Start** (or **Restart** if it was already running).

> The Options save and the Network save are two separate buttons. Both must be saved before restarting.

### 5 — Connect

The SSH username is always **`root`** regardless of your HA account name. Use the VM's LAN IP (visible in Proxmox or your router):

```powershell
ssh root@<HA-IP>
```

Accept the host fingerprint on first connect. You should land at a shell prompt inside the HA container.

---

## Deploying Mission Control files over SSH

Run these from your dev machine after SSH is working. Replace `<HA-IP>` with your HA instance's IP address.

### 1 — Create the target directories

```powershell
ssh root@<HA-IP> "mkdir -p /config/www/core_configurator /config/custom_components/core_configurator"
```

### 2 — Copy the integration and panel files

```powershell
scp -r "Z:\CodingProjects\Alleycat\MissionControl\Apps\Core_Configurator\HA_Component\custom_components\core_configurator" root@<HA-IP>:/config/custom_components/

scp -r "Z:\CodingProjects\Alleycat\MissionControl\Apps\Core_Configurator\HA_Component\www\core_configurator" root@<HA-IP>:/config/www/
```

### 3 — Append to configuration.yaml

SSH in and append the Mission Control sections:

```powershell
ssh root@<HA-IP>
```

```bash
cat >> /config/configuration.yaml << 'EOF'

# ─── Phase 1 — Core Configurator ───────────────────────────────────────────
core_configurator:
  registration_primary: !secret cc_registration_primary
  registration_secondary: !secret cc_registration_secondary
  alleycattv: !secret cc_alleycattv
  gbn: !secret cc_gbn
  proxmox: !secret cc_proxmox
  proxmox_node: !secret cc_proxmox_node

frontend:
  extra_module_url:
    - /local/core_configurator/core-configurator-client.js

panel_custom:
  - name: core-configurator-panel
    sidebar_title: Core Configurator
    sidebar_icon: mdi:lan
    url_path: core-configurator
    module_url: /local/core_configurator/core-configurator-panel.js
EOF
```

> If HA already has a `frontend:` block, the append creates a duplicate key and HA will refuse to start. Check with `tail -40 /config/configuration.yaml` — if there are two `frontend:` sections, edit the file with `vi /config/configuration.yaml` and merge the `extra_module_url` list into the existing block.

### 4 — Write secrets.yaml

Still in the SSH session, append your real service URLs:

```bash
cat >> /config/secrets.yaml << 'EOF'

# Core Configurator
cc_registration_primary: https://your-cloud-player-api.example.com
cc_registration_secondary: http://192.168.1.234:8090
cc_alleycattv: http://headless-alleycat-streaming-server.local
cc_gbn: http://192.168.1.206:8100
cc_proxmox: https://192.168.1.1:8006
cc_proxmox_node: pve
EOF
```

### 5 — Verify and restart

```bash
tail -30 /config/configuration.yaml
tail -15 /config/secrets.yaml
ha core restart
```

The **Core Configurator** tab appears in the HA sidebar after the restart. Open it and confirm the seeded URLs loaded. Edit them from the sidebar going forward — do not edit `secrets.yaml` again for URL changes.
