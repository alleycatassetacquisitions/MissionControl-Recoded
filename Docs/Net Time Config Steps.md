# Net Time Config Steps

Deploy **Net Time** as a Proxmox companion: a privileged Ubuntu LXC running **chrony** (NTP/SNTP on UDP **123**) plus a management API, and a small **host clock agent** on the Proxmox node so **Sync Now** works when the LXC cannot set the system clock.

PDN and FDN client sync is owned by those firmware teams — point SNTP at the printed LXC IP.

## What operators get (Core Configurator)

On the **Net Time** card:

| Control | Behavior |
| --- | --- |
| URL + API token → **Apply** | Stored in Core Configurator (`net_time` / `extra.token`) |
| **Confirm online** | HA → `net_time/health` + `net_time/status`. Shows online/offline with Mission Control, public pool status, stratum, and **wall clock in the configured timezone** (not raw UTC `…Z`) |
| **Timezone** dropdown | Common venue IANA zones (US/Canada first, then major world regions). **Set timezone** runs `timedatectl` inside the CT |
| **Sync Now** | Always available. Pushes **this PC’s** time (browser ISO-8601) via `POST /sync`. Tries the LXC first; if `date -s` is denied (normal on Proxmox), falls back to the **host clock agent** on the Proxmox node |

Status phrases:

- **able to connect to public NTP** — chrony has a usable public/pool source (or non-local tracking with stratum under 10)
- **no public NTP available** — offline / orphan (`local stratum 10`) mode

NTP itself is always UTC. The timezone setting affects operator display and the CT’s local clock presentation; SNTP clients still receive UTC.

## Install (new Proxmox CT)

Run on the **Proxmox node shell** (Datacenter → the host → **Shell**).

1. Copy `ProxmoxInstallFiles/install-net-time-proxmox.sh` to `/root/install-net-time-proxmox.sh` (ensure LF line endings; Windows SCP can introduce CRLF).
2. Prefer copying `Apps/Net_Time/Server_Component` to `/root/net-time-src` (no GitHub needed). The folder must contain `host_clock_agent.py`, `chrony_ops.py`, `main.py`, etc. at the **top level** of `net-time-src` (not nested under another `Server_Component` folder).
3. Run:

```bash
sed -i 's/\r$//' /root/install-net-time-proxmox.sh
chmod +x /root/install-net-time-proxmox.sh
NET_TIME_SRC=/root/net-time-src bash /root/install-net-time-proxmox.sh
```

4. Wait for `Done. CT … is ready.` The script prints CTID, LAN IP, API URL `:8720`, API token, and host clock agent URL `:8721`.

| Secret / Core Configurator field | Value |
| --- | --- |
| `cc_net_time` | `http://<printed-IP>:8720` |
| `cc_net_time_token` | the printed token |

NTP clients: `<printed-IP>` UDP **123**.

Defaults: Ubuntu 24.04, 1 core, 512 MB RAM, 4 GB disk, privileged CT, bridge `vmbr0`.

### What the installer starts

| Piece | Where | Port / path |
| --- | --- | --- |
| `chrony` | LXC | UDP **123** |
| `net-time` (FastAPI / uvicorn) | LXC `/opt/net_time` | TCP **8720** |
| `net-time-host-clock` | Proxmox **host** | TCP **8721** |

The CT env file `/etc/net-time.env` includes `NET_TIME_API_TOKEN` and `NET_TIME_HOST_CLOCK_URL` (Proxmox bridge IP `:8721`).

### Optional overrides

| Variable | Default | Purpose |
| --- | --- | --- |
| `CTID` | next free | Container ID |
| `NET_TIME_PORT` | `8720` | Management API port |
| `NET_TIME_HOST_CLOCK_PORT` | `8721` | Host clock agent port |
| `HOST_IP` | auto (bridge / `hostname -I`) | Address the CT uses for the host agent |
| `NET_TIME_API_TOKEN` | random | Skip generation |
| `NET_TIME_SRC` | _(empty)_ | Host path to `Server_Component` |
| `ROOT_PASSWORD` | `alleycat` | LXC root password |
| `SKIP_CONFIRM` | `0` | Set `1` to skip the 5-second cancel window |

## Why Sync Now uses a host agent

Proxmox LXC guests **share the host system clock**. Inside the CT, `date -s` / `chronyc settime` usually fail with `Operation not permitted`.

Do **not** add `lxc.cap.keep: sys_time` — it conflicts with Proxmox `lxc.cap.drop` and can prevent the CT from starting.

Instead, Sync Now:

1. Tries chronyc / `date` inside the LXC
2. If that fails, `POST`s to the host agent at `NET_TIME_HOST_CLOCK_URL` with the same Bearer token
3. The host agent sets the Proxmox host clock; chrony in the CT then serves that time to FDN/PDN clients

### Upgrade an existing CT (host agent + API)

If Net Time was installed before the host agent existed:

```powershell
# From your PC
scp "z:\CodingProjects\Alleycat\MissionControl\Apps\Net_Time\Server_Component\host_clock_agent.py" root@<PROXMOX-IP>:/root/host_clock_agent.py
scp "z:\CodingProjects\Alleycat\MissionControl\Apps\Net_Time\Server_Component\chrony_ops.py" root@<PROXMOX-IP>:/root/chrony_ops.py
scp "z:\CodingProjects\Alleycat\MissionControl\Apps\Net_Time\Server_Component\main.py" root@<PROXMOX-IP>:/root/main.py
scp "z:\CodingProjects\Alleycat\MissionControl\Apps\Net_Time\Server_Component\models.py" root@<PROXMOX-IP>:/root/models.py
scp "z:\CodingProjects\Alleycat\MissionControl\ProxmoxInstallFiles\upgrade-net-time-host-clock.sh" root@<PROXMOX-IP>:/root/upgrade-net-time-host-clock.sh
```

```bash
sed -i 's/\r$//' /root/upgrade-net-time-host-clock.sh
chmod +x /root/upgrade-net-time-host-clock.sh
HOST_IP=<PROXMOX-IP> CTID=<CTID> bash /root/upgrade-net-time-host-clock.sh
```

## Home Assistant

1. Deploy:
   - `Apps/Net_Time/HA_Component/custom_components/net_time/` → `/config/custom_components/net_time/`
   - `Apps/Core_Configurator/HA_Component/custom_components/core_configurator/` → `/config/custom_components/core_configurator/` (catalog key `net_time`)
   - `Apps/Core_Configurator/HA_Component/www/core_configurator/` → `/config/www/core_configurator/` (dropdown, Confirm, Sync Now, local time display)
2. Secrets (or set in the Core Configurator sidebar after first seed):

```yaml
cc_net_time: http://10.10.50.203:8720
cc_net_time_token: <printed-token>
```

3. Ensure `configuration.yaml` has `net_time: {}` and Core Configurator seed keys `net_time` / `net_time_token` (see [`HomeAssist/configuration.yaml`](../HomeAssist/configuration.yaml) and [`secrets.yaml.example`](../HomeAssist/secrets.yaml.example)).
4. Restart Home Assistant.
5. Settings → Devices & Services → add **Net Time** (install-only) if YAML import did not create the entry.
6. Hard-refresh the browser after updating `www/` files.

Websocket types (panel → HA → LXC API): `net_time/health`, `net_time/status`, `net_time/sync`, `net_time/set_timezone`.

## Operator checklist

1. Core Configurator → **Net Time** → paste URL + token → **Apply**
2. **Confirm online** — expect public NTP reachable when the venue has internet; status shows local wall time for the selected zone
3. Pick a timezone from the dropdown → **Set timezone**
4. At an offline venue (or to force PC time) → **Sync Now** — success may say **via Proxmox host**

## Smoke checks

```bash
# LXC API
curl http://<CT-IP>:8720/health
curl -H "Authorization: Bearer <token>" http://<CT-IP>:8720/status

# Host clock agent
curl http://<PROXMOX-IP>:8721/health
systemctl status net-time-host-clock

# Inside CT
pct enter <CTID>
systemctl status net-time chrony
chronyc tracking
chronyc sources -v
```

Expect:

- `/health` → `"status":"ok"`
- `/status` → `public_ntp` `reachable` or `unavailable`, plus `timezone`
- Host agent `/health` → `"service":"net_time_host_clock"`
- `chronyc sources` with `^*` on a public peer when online
