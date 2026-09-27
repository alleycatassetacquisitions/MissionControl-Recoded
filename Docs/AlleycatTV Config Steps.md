# AlleycatTV Config Steps

Deploy AlleycatTV as three pieces in **dependency order**:

1. **Proxmox content server** (media + playlists — no MQTT)
2. **Home Assistant integration** (fabric presence + MQTT commands + Content Manager proxy)
3. **TV Pi SD cards** (distro tool on a prep PC)

Prerequisites: Home Assistant OS with **Mosquitto** + HA `mqtt` already working (Phase 5a in [`Home Assistant Config Steps.md`](Home%20Assistant%20Config%20Steps.md)). Shared HA Helpers must be on HA before AlleycatTV.

Home Assistant is the **only** MQTT command publisher. The content LXC must not open a Mosquitto client.

---

## Deployment order (checklist)

| Step | Where | Done when |
| --- | --- | --- |
| A. Content LXC | Proxmox host | `curl http://<IP>/health` → `"status":"ok","mqtt":false` |
| B. Core Configurator URL | HA | `alleycattv` = `http://<IP>` |
| C. HA integration + panels | HA | AlleycatTV + AlleycatTV Content in sidebar |
| D. Flash Pis | Prep PC | Each Pi publishes `mc/tv/status/{pi_id}` |
| E. Smoke test | HA | Play/stop Broadcast Group service publishes; Pi reacts |

---

## A. Install content server (Proxmox)

Run this on the **Proxmox node shell** (not inside a guest).

1. Copy `Docs/install-alleycattv-proxmox.sh` onto the host as `/root/install-alleycattv-proxmox.sh`.
2. Prefer a local checkout (no GitHub login):

```bash
chmod +x /root/install-alleycattv-proxmox.sh
ATV_SRC=/root/MissionControl/Apps/AlleycatTV/Server_Component \
  bash /root/install-alleycattv-proxmox.sh
```

3. Wait for `Done. CT … is ready.` Note the printed LAN IP.
4. Confirm from any PC on the LAN:

```bash
curl http://<printed-IP>/health
# → {"status":"ok","media_base":"…","mqtt":false}
```

5. Open `http://<printed-IP>/manage` for the content UI (ops). Operator day-to-day content work should go through the HA **AlleycatTV Content** panel (proxy).

### Defaults

| Setting | Default |
| --- | --- |
| Template | Ubuntu 24.04 standard |
| CPU / RAM / disk | 2 cores / 2 GB / 60 GB on `local-lvm` |
| Bridge | `vmbr0` (DHCP) |
| HTTP | nginx → uvicorn `:8000` on port **80** |
| Root password | `alleycat` |

### Optional overrides

| Variable | Default | Purpose |
| --- | --- | --- |
| `CTID` | next free | Container ID |
| `STORAGE` | `local-lvm` | Root disk |
| `DISK_SIZE` | `60` | GiB (raise for large libraries) |
| `ATV_SRC` | _(empty)_ | Host path to `Server_Component` (recommended) |
| `REPO_URL` | Mission Control git URL | Used only if `ATV_SRC` unset |
| `ROOT_PASSWORD` | `alleycat` | Console / SSH |
| `SKIP_CONFIRM` | `0` | `1` to skip countdown |

### Updating content-server code later

From your PC, sync `Server_Component` to the Proxmox host, then into the LXC (CT id from install output):

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\AlleycatTV\Server_Component" root@<PROXMOX-IP>:/root/alleycattv-src
```

On the Proxmox host:

```bash
tar -C /root/alleycattv-src -cf - . | pct exec <CTID> -- tar -C /opt/alleycattv/server -xf -
pct exec <CTID> -- chown -R alleycattv:alleycattv /opt/alleycattv/server
pct exec <CTID> -- systemctl restart alleycattv-server nginx
curl http://<IP>/health
```

---

## B. Point Core Configurator at the content server

| Field | Value |
| --- | --- |
| Core Configurator key `alleycattv` / secret `cc_alleycattv` | `http://<printed-IP>` (no path) |

Seed via [`HomeAssist/secrets.yaml.example`](../HomeAssist/secrets.yaml.example) on first boot, or edit the Core Configurator sidebar after the entry exists.

---

## C. Deploy AlleycatTV onto Home Assistant

Mosquitto + Shared Helpers must already be installed (Phases 5a–5b).

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\AlleycatTV\HA_Component\custom_components\alleycattv" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\AlleycatTV\HA_Component\www\alleycattv" root@<HA-IP>:/config/www/
```

Merge from [`HomeAssist/configuration.yaml`](../HomeAssist/configuration.yaml) into `/config/configuration.yaml`:

- the `alleycattv: {}` block (loads the custom component / proxy on start; bare `alleycattv:` is YAML null and will not load)
- the AlleycatTV `panel_custom` blocks

Restart:

```bash
ha core restart
```

1. On first boot with `alleycattv: {}`, the install-only config entry is imported automatically. You can also **Settings → Devices & services → Add integration → AlleycatTV**.
2. Confirm sidebar: **AlleycatTV** and **AlleycatTV Content**.
3. Hard-refresh the browser. Content panel Refresh should list media/groups via the HA proxy (no LAN `fetch`).

If Content shows “Proxy not registered” or AlleycatTV shows “Unknown command”, the Python package is not loaded: use `alleycattv: {}` (not a bare key), redeploy `custom_components/alleycattv`, restart HA, then confirm **AlleycatTV** appears under Devices & services.

Playback services (examples):

- `alleycattv.play_broadcast_group` / `stop_broadcast_group` with `broadcast_group_id`
- `alleycattv.interrupt_pi` with `pi_id` + `file_url`

Topics: `mc/tv/…` — see [`MQTT Communication Principles.md`](MQTT%20Communication%20Principles.md).

---

## D. Flash TV Pi SD cards (prep PC)

Operators run the distro CLI on a Windows (or Linux) prep PC. Do **not** flash Broadcast Group membership (Phase 7).

A successful flash is **plug-and-play**: after first boot the Pi joins Wi‑Fi (preferred over Ethernet), creates the Pi OS user, enables SSH password login, installs the AlleycatTV player from a bootfs bundle, and publishes MQTT presence so **Endpoint** chips appear in the AlleycatTV panel.

### Prerequisites

| Need | Notes |
| --- | --- |
| Raspberry Pi OS **Lite 64-bit** (Trixie) | Official `.img.xz` is fine — do **not** convert to ISO |
| [Raspberry Pi Imager](https://www.raspberrypi.com/software/) | Required on Windows (`rpi-imager.exe`; flash tool locates it under `Program Files\Raspberry Pi Ltd\Imager`) |
| Elevated PowerShell | Imager needs admin to write disks |
| OpenSSL | Git for Windows provides `openssl` (used to hash the Pi OS password for `userconf.txt`) |
| Mosquitto login (Phase 5a) | **Must be saved** in the add-on Configuration → `logins`. Venue default: user `alleycatTV` / password `alleycat` |

### Flash command

```powershell
cd z:\CodingProjects\Alleycat\MissionControl\Apps\AlleycatTV\Client_Component\distro
py -3 flash.py --image .\2026-09-15-raspios-trixie-arm64-lite.img.xz
```

Dry run (no disk write):

```powershell
py -3 flash.py --dry-run --inject-only
```

### Session prompts (venue defaults)

Enter once per flash session (reused for every card):

| Prompt | Example / venue default | Rules |
| --- | --- | --- |
| Content server URL | `http://192.168.1.173` | Must include `http://` |
| MQTT broker | `192.168.1.11` | HAOS LAN IP — **no** `http://` |
| MQTT port | `1883` | |
| MQTT username | `alleycatTV` | Exact Mosquitto `logins` user |
| MQTT password | `alleycat` | Exact Mosquitto `logins` password — blank → Pi gets MQTT `rc=5` and never appears in HA |
| Pi OS username | `alleycat` | SSH / kiosk user |
| Pi OS password | `alleycat` | SSH password |

Per card:

| Prompt | Example |
| --- | --- |
| Pi ID | `Endpoint-1` (becomes fabric device id / panel chip) |
| Hostname | defaults to Pi ID |
| Wi‑Fi SSID / PSK | venue Wi‑Fi (required for headless TV Pis) |

Confirm disk erase with exact `YES` (case-sensitive).

### What the tool writes

After Imager finishes, the tool waits for `bootfs` (often `D:\`) and injects:

| Bootfs artifact | Purpose |
| --- | --- |
| `user-data` + `meta-data` | cloud-init: hostname, user, `enable_ssh`, `ssh_pwauth`, first-boot install |
| `userconf.txt` + empty `ssh` | Legacy fallbacks |
| `network-config` | Netplan v2 — Wi‑Fi preferred (route metric 100) over Ethernet (700) |
| `alleycattv.env` | Per-unit MQTT / content server / Pi ID |
| `alleycattv-client.tgz` | Player sources |
| `alleycattv-firstboot.sh` | Runs `install.sh --from-env` once |

**Success line must look like:** `Injected config for Endpoint-1 into D:\` (a real drive letter).  
**Failure:** inject into a Temp path means config never reached the card — reseat the reader and re-run, or `py -3 flash.py --inject-only` and enter `D:\` when asked.

### First boot

1. Safely eject, insert SD in the Pi, power on. First boot can take **several minutes** (apt + player install).
2. Pi should skip the OS setup wizard and land on a login / kiosk path.
3. SSH: `ssh alleycat@<pi-ip>` (password from flash). After a reflash, clear a stale host key if OpenSSH complains:

```powershell
ssh-keygen -R <pi-ip>
ssh alleycat@<pi-ip>
```

4. Confirm player + MQTT:

```bash
systemctl is-active alleycattv-player   # active
journalctl -u alleycattv-player -n 30 --no-pager
# expect MQTT connected — NOT "MQTT connect failed rc=5"
curl http://192.168.1.173/health
```

5. In HA **AlleycatTV** panel, hard-refresh — chip for the Pi ID (e.g. `Endpoint-1`) should appear from `mc/tv/status/{pi_id}`.

Empty playlist / “Zone playlist has no playable items” is normal until Part E / Phase 7 assigns a broadcast group.

### Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Setup wizard on first boot | Missing / ignored cloud-init user | Full reflash with current `flash.py` (Trixie needs `user-data`, not only `userconf.txt`) |
| Online but IP `127.0.1.1` | Wi‑Fi never applied | Trixie ignores `wpa_supplicant.conf`; need `network-config` **before** first boot, or `nmcli` on console |
| Host key verification failed | Reflashed Pi, new SSH host key | `ssh-keygen -R <ip>` then reconnect |
| SSH password rejected | User/SSH not applied by cloud-init | Reflash with current tool; or set password on HDMI console |
| `MQTT connect failed rc=5` | Mosquitto rejected auth | Save `logins` in Mosquitto add-on, then put the same user/pass in `/etc/alleycattv.env` and `sudo systemctl restart alleycattv-player` |
| Inject to Temp / “no boot mount” | Windows slow to remount `bootfs` | Wait for `bootfs` in Explorer; enter `D:\` at prompt; tool now polls up to 90s |
| Panel “No devices yet” | No presence publish | Fix MQTT `rc=5` first; confirm `alleycattv-player` is `active` |
| Imager: destination not removable | USB reader looks like fixed disk | Tool passes `--enable-writing-system-drives`; own picker still blocks system disks |

### Notes

- Pi MQTT broker must be the **Home Assistant Mosquitto** host (Phase 5a), not a Proxmox Mosquitto LXC.
- Rewriting bootfs after first boot does **not** re-run cloud-init — full re-flash for identity/network/user changes that must apply at first boot. Per-unit MQTT tweaks can be edited live in `/etc/alleycattv.env`.
- Optional golden-image shortcut: bake once, clone `.img`, then `flash.py --inject-only` for per-unit identity only.

---

## E. Smoke test

1. Confirm the Pi chip is online in the **AlleycatTV** panel (Part D). Playlist warnings alone are OK at this stage.
2. Content: upload a short video via **AlleycatTV Content** or `/manage`; create a broadcast group + playlist id (e.g. `lobby`).
3. Temporarily set membership on the Pi until Phase 7 owns it:

```bash
sudo sed -i 's/^ALLEYCATV_BROADCAST_GROUP_ID=.*/ALLEYCATV_BROADCAST_GROUP_ID=lobby/' /etc/alleycattv.env
sudo systemctl restart alleycattv-player
```

4. From HA: call `alleycattv.play_broadcast_group` with `broadcast_group_id: lobby`.
5. Pi plays; `media_player` / status JSON updates.
6. Call `stop_broadcast_group` — playback stops; retained desired topic updates.

---

## Ownership reminder

| Piece | Owns |
| --- | --- |
| HA `alleycattv` | MQTT commands, presence via fabric, Content Manager proxy |
| Proxmox content server | Files + playlists only |
| Pi client | mpv + subscribe `mc/tv/cmd/…` |
| Broadcast Group Controller | Membership + area placement — **Phase 7** |

App overview: [`Apps/AlleycatTV/README.md`](../Apps/AlleycatTV/README.md)  
HA phase slice: [`Home Assistant Config Steps.md` — Phase 6](Home%20Assistant%20Config%20Steps.md#phase-6--alleycattv-on-the-fabric)
