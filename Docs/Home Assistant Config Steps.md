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

1. Wait for `Done. VM … is ready.` First boot takes a few minutes.
2. On any computer on the same LAN, open [http://homeassistant.local](http://homeassistant.local) or [http://homeassistant.local:8123](http://homeassistant.local:8123).

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


| Device                | Value                                         |
| --------------------- | --------------------------------------------- |
| Memory                | 8.00 GiB                                      |
| Processors            | 4 (1 socket, 4 cores) `[x86-64-v2-AES]`       |
| BIOS                  | OVMF (UEFI)                                   |
| EFI                   | `efitype=4m`, Pre-Enroll keys **off**         |
| Display               | Default                                       |
| Machine               | q35                                           |
| SCSI Controller       | VirtIO SCSI single                            |
| CD/DVD Drive (ide2)   | none, media=cdrom                             |
| Hard Disk (scsi0)     | `local-lvm`, discard=on, iothread=1, size=32G |
| Network Device (net0) | virtio, bridge=`vmbr0`, firewall=1            |
| EFI Disk              | `local-lvm`, efitype=4m, size=4M              |


The MAC address and disk IDs (`vm-*-disk-*`) are generated per VM. Do not copy them from another machine.

## Proxmox VM options

Name the VM `Home-Assistant`.


| Option                      | Value                         |
| --------------------------- | ----------------------------- |
| Start at boot               | Yes                           |
| Start/Shutdown order        | order=any                     |
| OS Type                     | Linux 7.x - 2.6 Kernel        |
| Boot Order                  | scsi0                         |
| Use tablet for pointer      | Yes                           |
| Hotplug                     | Disk, Network, USB            |
| ACPI support                | Yes                           |
| KVM hardware virtualization | Yes                           |
| Freeze CPU at startup       | No                            |
| Use local time for RTC      | Default (Enabled for Windows) |
| RTC start date              | now                           |
| QEMU Guest Agent            | Default (Disabled)            |
| Protection                  | No                            |
| Spice Enhancements          | none                          |
| VM State storage            | Automatic                     |
| AMD SEV                     | Default (Disabled)            |
| Intel TDX                   | Default (Disabled)            |


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

The SSH username is always `root` regardless of your HA account name. Use the VM's LAN IP (visible in Proxmox or your router):

```powershell
ssh root@<HA-IP>
```

Accept the host fingerprint on first connect. You should land at a shell prompt inside the HA container.

---

## Deploy Mission Control files onto HA

SSH must already work (section above). Copy **into** `/config/` — never overwrite the whole `/config` tree with the repo `HomeAssist\` folder.

### What lands where

See [`File Structure.md` — On Home Assistant](File%20Structure.md#on-home-assistant) for the full map. Short version:

| From repo | To HA |
| --- | --- |
| `…\custom_components\<domain>\` | `/config/custom_components/<domain>/` |
| `…\www\<name>\` | `/config/www/<name>/` |
| Merge `HomeAssist/configuration.yaml` sections | `/config/configuration.yaml` |
| Secrets from `secrets.yaml.example` | `/config/secrets.yaml` |

### Phase 4 — Core Configurator + Shared Helpers + Registration

From PowerShell on your PC (`<HA-IP>` = LAN address of the HA VM):

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\Libraries\Shared_HA_Helpers\HA_Component\custom_components\shared_libraries" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Libraries\Shared_HA_Helpers\HA_Component\www\shared_libraries" root@<HA-IP>:/config/www/

scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Core_Configurator\HA_Component\custom_components\core_configurator" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Core_Configurator\HA_Component\www\core_configurator" root@<HA-IP>:/config/www/

scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Registration\HA_Component\custom_components\registration" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Registration\HA_Component\www\registration" root@<HA-IP>:/config/www/
```

Then merge [`HomeAssist/configuration.yaml`](../HomeAssist/configuration.yaml) into `/config/configuration.yaml` (keep `default_config`, themes, automations includes; add `frontend.extra_module_url`, `core_configurator` seed, both `panel_custom` entries). Fill `/config/secrets.yaml` from [`secrets.yaml.example`](../HomeAssist/secrets.yaml.example) with MCS URL/token and Central URLs.

Restart and hard-refresh the browser:

```bash
ha core restart
```

### After restart

1. Core Configurator entry: delete + re-add (or first import) so YAML/secrets re-seed MCS URL + token.
2. Settings → Devices & Services → Add **Registration** (install-only — no token field).
3. Confirm sidebar panels: Core Configurator, Registration.
4. Registration **Sync Now** should load the roster (Role / NeoCorp / Faction via MCS field mapping).

MCS itself is deployed on Proxmox, not HA — see [`Master Control Server Config Steps.md`](Master%20Control%20Server%20Config%20Steps.md).

### Phase 5 — Mosquitto + Shared Helpers (fabric) + Digital Node Nexus

MQTT for Mission Control uses the **official Mosquitto broker add-on** on Home Assistant OS (not a custom broker, not a Proxmox Mosquitto LXC). DNN and the fabric talk only through HA’s `mqtt` integration.

#### 5a. Install Mosquitto and connect the MQTT integration

1. **Settings → Add-ons → Add-on store** → search **Mosquitto broker** → **Install**.
2. Open the add-on → **Configuration**:
   - Under `logins`, add a local user (username + password), then **Save**.  
     Venue default used by AlleycatTV Pi flashes:

     ```yaml
     logins:
       - username: alleycatTV
         password: alleycat
     ```

     If you skip Save, Pis connect with blank/wrong creds and fail with MQTT **`rc=5` (Not authorized)** — they will not appear in AlleycatTV.
3. **Start** the add-on. Confirm it is running (Log tab shows Mosquitto started).
4. Enable **Start on boot** (and **Watchdog** if you want auto-restart).
5. **Settings → Devices & services → Add integration → MQTT**.
6. When asked how to connect, choose **Use the official Mosquitto Mqtt Broker app.**  
   HA should discover the add-on and finish the MQTT integration setup.  
   (If discovery fails: choose manual entry and use host `core-mosquitto`, port `1883`, and the user/password from step 2.)
7. Confirm **MQTT** appears under Devices & services and is not in an error state.

Official docs: [Mosquitto broker add-on](https://github.com/home-assistant/addons/tree/master/mosquitto) · [MQTT integration](https://www.home-assistant.io/integrations/mqtt/)

#### 5b. Deploy Shared Helpers + Digital Node Nexus

Redeploy Shared HA Helpers (includes `fabric.py`), then DNN:

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\Libraries\Shared_HA_Helpers\HA_Component\custom_components\shared_libraries" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Libraries\Shared_HA_Helpers\HA_Component\www\shared_libraries" root@<HA-IP>:/config/www/

scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Digital_Node_Nexus\HA_Component\custom_components\digital_node_nexus" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Digital_Node_Nexus\HA_Component\www\digital_node_nexus" root@<HA-IP>:/config/www/
```

Merge the Digital Node Nexus `panel_custom` block from [`HomeAssist/configuration.yaml`](../HomeAssist/configuration.yaml). Restart:

```bash
ha core restart
```

1. Settings → Devices & services → Add **Digital Node Nexus** (install-only). If setup says MQTT is not ready, finish **5a** first; DNN will retry.
2. Confirm sidebar: Digital Node Nexus.
3. Hard-refresh the browser. **Refresh** on the DNN panel should load the MCS roster (no “Unknown command”).
4. FDNs that publish `mc/dnn/status/{id}` (to the Mosquitto broker) appear as devices with presence sensors.
5. Page composer can target FDN / all / broadcast id / MCS player / role|NeoCorp filter.

FDN / Pi firmware must use the **HA host LAN IP** (or a DNS name that resolves to it) and Mosquitto’s listener port (**1883** by default), with the same credentials as the add-on `logins` entry.

### Phase 6 — AlleycatTV on the fabric

TV Pis join the same MQTT fabric as FDNs. Home Assistant is the **only** command publisher. The content server stays on Proxmox and does **not** open an MQTT client.

**Full deployment walkthrough (Proxmox LXC → HA → Pi SD flash):**  
[`AlleycatTV Config Steps.md`](AlleycatTV%20Config%20Steps.md)

#### 6a. Content server (Proxmox)

On the Proxmox **node** shell:

```bash
ATV_SRC=/root/MissionControl/Apps/AlleycatTV/Server_Component \
  bash /root/install-alleycattv-proxmox.sh
```

(Copy `Docs/install-alleycattv-proxmox.sh` to `/root/` first.) Confirm `curl http://<IP>/health` returns `"mqtt": false`, then set Core Configurator **alleycattv** to `http://<IP>`.

#### 6b. Deploy AlleycatTV HA integration

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\AlleycatTV\HA_Component\custom_components\alleycattv" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\AlleycatTV\HA_Component\www\alleycattv" root@<HA-IP>:/config/www/
```

Merge from [`HomeAssist/configuration.yaml`](../HomeAssist/configuration.yaml): the `alleycattv: {}` block **and** the AlleycatTV `panel_custom` entries. Restart:

```bash
ha core restart
```

1. Settings → Devices & services → Add **AlleycatTV** (install-only). MQTT must already be ready (Phase 5a). Sidebar panels without this entry → “Unknown command” / “Proxy not registered”.
2. Sidebar: **AlleycatTV** and **AlleycatTV Content**.
3. Pis that publish `mc/tv/status/{pi_id}` appear as devices; playback commands use `alleycattv.play_broadcast_group` / `stop_broadcast_group`.

#### 6c. Flash TV Pi SD cards (prep PC)

Plug-and-play flash (Trixie Lite `.img.xz`, cloud-init, player bundle, MQTT presence):

```powershell
cd z:\CodingProjects\Alleycat\MissionControl\Apps\AlleycatTV\Client_Component\distro
py -3 flash.py --image .\2026-09-15-raspios-trixie-arm64-lite.img.xz
```

Venue flash prompts (must match Phase 5a Mosquitto `logins`):

| Field | Venue example |
| --- | --- |
| Content server | `http://<content-LXC-IP>` |
| MQTT broker | HA LAN IP (e.g. `192.168.1.11`) — no `http://` |
| MQTT user / pass | `alleycatTV` / `alleycat` |
| Pi OS user / pass | `alleycat` / `alleycat` |

Confirm inject lands on `bootfs` (e.g. `D:\`), not a Temp folder. First boot installs the player; AlleycatTV panel chips appear when `mc/tv/status/{pi_id}` is published (MQTT `rc=5` means bad/missing Mosquitto login).

Do **not** flash Broadcast Group membership — assign it in the **Broadcast Groups** panel after the Pi appears.

Full procedure + troubleshooting: [`AlleycatTV Config Steps.md` § D](AlleycatTV%20Config%20Steps.md#d-flash-tv-pi-sd-cards-prep-pc) · App README: [`Apps/AlleycatTV/README.md`](../Apps/AlleycatTV/README.md)

### Phase 7 — Broadcast Group Controller

One placement service for the venue. Physical = HA Area. Membership = Broadcast Group (not Labels — see app README).

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Broadcast_Group_Controller\HA_Component\custom_components\broadcast_group_controller" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Broadcast_Group_Controller\HA_Component\www\broadcast_group_controller" root@<HA-IP>:/config/www/
```

Merge from [`HomeAssist/configuration.yaml`](../HomeAssist/configuration.yaml): `broadcast_group_controller: {}` and the Broadcast Groups `panel_custom` entry. Redeploy AlleycatTV panels/www if you have not already (full Content + Player panels). Restart HA.

1. Settings → Devices & services → Add **Broadcast Group Controller**.
2. Sidebar **Broadcast Groups**: select a TV Pi or FDN → Set area → Set broadcast group (e.g. `lobby`).
3. Pi receives `mc/tv/cmd/device/{id}/membership` and resubscribes to `cmd/broadcast/lobby/#`.
4. AlleycatTV Content owns playlist buckets for that id; Player panel owns play/stop/interrupt.

App README: [`Apps/Broadcast_Group_Controller/README.md`](../Apps/Broadcast_Group_Controller/README.md)

