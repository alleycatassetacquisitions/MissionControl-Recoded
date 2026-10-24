# Venue Install (one-line)

Install Home Assistant OS, Mission Control companion LXCs, HA components, and Core Configurator secrets from the **Proxmox node shell**.

## Online (preferred)

```bash
bash <(curl -fsSL https://github.com/alleycatassetacquisitions/MissionControl-Recoded/releases/latest/download/install-mission-control.sh)
```

Private release: `GH_TOKEN=…` in the environment before the curl.

The bootstrap downloads `mission-control-venue.tar.gz`, verifies `SHA256SUMS` when present, stages `/root/mission-control-src`, then runs the orchestrator.

## Offline / USB / SCP (Windows PowerShell)

`bash` is **not** available in PowerShell by default. Package with Git Bash (or WSL), then copy to Proxmox with PowerShell `scp`. The install script itself runs **only on the Proxmox host shell**, not on your PC.

If the venue Proxmox host has **no internet**, stage the Linux CT template and (optionally) the Home Assistant OS image **before** running the installer. Without the CT template the installer stops early with an error.

### Where to put offline files on the Proxmox host

| What | Exact path on Proxmox | Notes |
| --- | --- | --- |
| **Ubuntu 24.04 LXC template** (required offline) | `/var/lib/vz/template/cache/` | File looks like `ubuntu-24.04-standard_24.04-2_amd64.tar.zst`. This is Proxmox “local” storage template cache — **not** an ISO for bare-metal install. |
| **Home Assistant OS image** (required if HAOS cannot download) | `/root/` (recommended) | File looks like `haos_ova-16.2.qcow2.xz` (or `.qcow2`). Pass the full path with `HAOS_IMAGE=…` when starting the installer. |
| **Venue install bundle** | `/root/mission-control-venue/` | From `package-venue-bundle.sh` / SCP (see below). |

Confirm the CT template is visible to Proxmox:

```bash
ls -lh /var/lib/vz/template/cache/ubuntu-24.04*
pveam list local
```

### Offline — Linux CT template (required)

Companion LXCs need an **Ubuntu 24.04** container template. On a machine that *does* have internet (lab Proxmox, or download then USB/SCP):

```bash
# On any networked Proxmox node:
pveam update
pveam available --section system | grep ubuntu-24.04-standard
pveam download local ubuntu-24.04-standard_24.04-2_amd64.tar.zst   # use the exact name from the list
```

Copy the resulting `.tar.zst` onto the **venue** host:

```powershell
# From Windows → venue Proxmox (PowerShell scp is fine)
scp "ubuntu-24.04-standard_24.04-2_amd64.tar.zst" root@10.10.50.205:/var/lib/vz/template/cache/
```

Or on the venue host shell after USB copy:

```bash
cp /media/usb/ubuntu-24.04-standard_*.tar.zst /var/lib/vz/template/cache/
pveam list local
```

### Offline — Home Assistant OS image

Download the KVM/Proxmox image from [Home Assistant OS releases](https://github.com/home-assistant/operating-system/releases) (`haos_ova-*.qcow2.xz`). Copy it to the venue host:

```powershell
scp "haos_ova-16.2.qcow2.xz" root@10.10.50.205:/root/
```

Run the installer with that path:

```bash
HAOS_IMAGE=/root/haos_ova-16.2.qcow2.xz bash /root/mission-control-venue/install-mission-control.sh
```

(Use the real filename/version you copied.)

### Package and copy

**1 — Package on the PC** (Git Bash or WSL — not PowerShell; needs network once to fetch sidebar plugins):

```bash
# Git Bash:
cd /z/CodingProjects/Alleycat/MissionControl   # or your repo path
bash ProxmoxInstallFiles/package-venue-bundle.sh
```

Or from PowerShell, call Git Bash explicitly:

```powershell
& "C:\Program Files\Git\bin\bash.exe" -lc "cd /z/CodingProjects/Alleycat/MissionControl && bash ProxmoxInstallFiles/package-venue-bundle.sh"
```

**2 — Copy to Proxmox** (PowerShell is fine):

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\dist\mission-control-venue" root@10.10.50.205:/root/
```

**3 — Run the installer on Proxmox** (Proxmox UI → host → Shell, or SSH into Proxmox):

```bash
bash /root/mission-control-venue/install-mission-control.sh
```

Do **not** run that last `bash /root/...` line in Windows PowerShell — `/root/` only exists on the Proxmox host.

## What the orchestrator does

1. **Proxmox host prep** — switches APT to **pve-no-subscription**, disables enterprise repos, patches the “No valid subscription” UI nag (APT hook so it sticks), then **`apt-get update` + `dist-upgrade`** so the node is on current patches ([Proxmox Config Steps](Proxmox%20Config%20Steps.md) § B + § C). Skip prep with `SKIP_PVE_HOST_PREP=1`, or skip only the upgrade with `SKIP_PVE_UPGRADE=1`.
2. Checks for an Ubuntu CT template under `/var/lib/vz/template/cache/` (or internet to download one) — fails early offline with instructions if missing.
3. Creates the **Home Assistant OS** VM (unless one named `Home-Assistant` already exists).
4. **Prints the detected HA LAN IP** (QEMU guest agent / DNS / ARP) and pauses for onboarding + Terminal & SSH (paste the printed deploy public key, port 22; Enter accepts the detected IP).
5. Creates **MCS**, **AlleycatTV**, **GBN**, **Net Time** LXCs (captures URLs/tokens).
6. Installs the **venue update agent** on the Proxmox host (`:8722`).
7. Creates a Proxmox API token (`hass@pve!missioncontrol`, role `PVEVMUser`) unless `PROXMOX_TOKEN_SECRET` is already set.
8. Prompts for **Central** primary/secondary URLs (or use `CENTRAL_PRIMARY` / `CENTRAL_SECONDARY` env). Secondary is optional — press Enter to leave it empty when there is no LAN mirror (do not keep a dead IP).
9. Copies all `custom_components` / `www` / themes / **mc-shell** (custom-sidebar + card-mod) into HA, writes `secrets.yaml`, merges configuration seed, force-reseeds Core Configurator.
10. Best-effort **Mosquitto** + **MQTT**, **Alleycat** default theme, **HACS** component (when HA can reach GitHub), sidebar title **Mission Control**.

After HA is up, Registration auto-pushes the peer snapshot to MCS on Core Configurator Save (peer keys) and on `registration.sync_now`; MCS fans out to GBN / Net Time. See [`Master Control Server Config Steps.md`](Master%20Control%20Server%20Config%20Steps.md#peer-push--fan-out-smoke-test-on-proxmox-host).

State is stored at `/root/mission-control-install-state.json`.

## Remaining operator steps (after Done)

1. Settings → Devices & services → Add **Proxmox VE** (node/VM sensors). Use host IP, user `hass`, realm PVE, token id `missioncontrol`, same secret as Core Configurator / `secrets.yaml`.
2. Settings → Devices & services → Add **HACS** if prompted → complete the one-time GitHub device-code authorize (sidebar title already works without this).
3. Hard-refresh the browser (Ctrl+Shift+R). Confirm sidebar says **Mission Control** and Profile theme is **Alleycat** (or Backend-selected).
4. Flash AlleycatTV Pis / point FDN firmware at HA MQTT (`alleycatTV` / `alleycat`).

Redeploy into an existing HA (after pulling a newer bundle):

```bash
RESUME=ha-deploy bash /root/mission-control-venue/install-mission-control.sh
```

## Updates

**UI:** Core Configurator → **Venue updates** card → **Check for GitHub Update** → Install if available.

**CLI:**

```bash
bash /root/mission-control-src/ProxmoxInstallFiles/update-mission-control.sh --check
bash /root/mission-control-src/ProxmoxInstallFiles/update-mission-control.sh --yes
```

Offline update: `BUNDLE=/path/to/mission-control-venue bash …/update-mission-control.sh --yes`

Updates preserve CT IDs, IPs, and API tokens (in-place code push).

## Building a release locally

Same as Offline step 1 (Git Bash / WSL). Output:

- `dist/mission-control-venue/` (folder to SCP)
- `dist/mission-control-venue.tar.gz`
- `dist/install-mission-control.sh`
- `dist/SHA256SUMS`

CI publishes the same artifacts on every push to `main` (workflow `venue-release.yml`). Packaging fetches `custom-sidebar` + `card-mod` into `HomeAssist/www/mc-shell/`.

## Per-app scripts

Individual installers remain available under [`ProxmoxInstallFiles/`](../ProxmoxInstallFiles/) for partial installs. Prefer the venue orchestrator for a full site.
