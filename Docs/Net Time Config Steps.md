# Net Time Config Steps

Deploy **Net Time** as a Proxmox LXC. It is the Mission Control LAN NTP authority (chrony on UDP 123) plus a small management API for Core Configurator (Confirm online / public pool status / Sync Now).

PDN and FDN client sync is owned by those firmware teams — point SNTP at the printed LXC IP.

## Install (Proxmox)

Run on the **Proxmox node shell** (Datacenter → the host → **Shell**).

1. Copy `ProxmoxInstallFiles/install-net-time-proxmox.sh` to `/root/install-net-time-proxmox.sh`.
2. Prefer copying `Apps/Net_Time/Server_Component` as `/root/net-time-src` (no GitHub needed).
3. Run:

```bash
chmod +x /root/install-net-time-proxmox.sh
NET_TIME_SRC=/root/net-time-src bash /root/install-net-time-proxmox.sh
```

4. Wait for `Done. CT … is ready.` The script prints CTID, LAN IP, API URL `:8720`, and API token.

| Secret / Core Configurator field | Value |
| --- | --- |
| `cc_net_time` | `http://<printed-IP>:8720` |
| `cc_net_time_token` | the printed token |

NTP clients: `<printed-IP>` UDP **123**.

The CT is **privileged**. Sync Now needs `CAP_SYS_TIME`. Do **not** add `lxc.cap.keep` (it conflicts with Proxmox `lxc.cap.drop` and can prevent the CT from starting). If Sync Now returns `Operation not permitted`, remove `sys_time` from the drop list instead:

```bash
# Inspect
cat /etc/pve/lxc/105.conf | grep -E 'cap\.(drop|keep)'
# If sys_time appears on an lxc.cap.drop line, edit that line and delete only "sys_time"
nano /etc/pve/lxc/105.conf
pct start 105   # or pct reboot 105 if it is already running
```

Defaults: Ubuntu 24.04, 1 core, 512 MB RAM, 4 GB disk.

Note: LXC guests often share the Proxmox host clock. When the venue has internet, chrony stratum ≤9 means public NTP is working and Sync Now is unnecessary. Sync Now is for offline venues once `sys_time` is allowed.

### Optional overrides

| Variable | Default | Purpose |
| --- | --- | --- |
| `CTID` | next free | Container ID |
| `NET_TIME_PORT` | `8720` | Management API port |
| `NET_TIME_API_TOKEN` | random | Skip generation |
| `NET_TIME_SRC` | _(empty)_ | Host path to `Server_Component` |
| `ROOT_PASSWORD` | `alleycat` | LXC root password |
| `SKIP_CONFIRM` | `0` | Set `1` to skip the 5-second cancel window |

## Home Assistant

1. Deploy files (see SCP list in the repo README / File Structure):
   - `custom_components/net_time/`
   - Updated `custom_components/core_configurator/` (catalog includes Net Time)
   - Updated `www/core_configurator/` (Confirm / Sync Now on the Net Time card)
2. Add secrets (or set them in the Core Configurator sidebar after first seed):

```yaml
cc_net_time: http://10.10.50.203:8720
cc_net_time_token: <printed-token>
```

3. Ensure `configuration.yaml` has `net_time: {}` and the Core Configurator seed keys `net_time` / `net_time_token`.
4. Restart Home Assistant.
5. Settings → Devices & Services → add **Net Time** (install-only) if YAML import did not create the entry.

## Operator flow (Core Configurator)

1. Open **Core Configurator** → **Net Time** card.
2. Paste URL + API token → **Apply**.
3. **Confirm online** — Mission Control must reach the LXC (`/health` + `/status`).
4. Status line:
   - **able to connect to public NTP** — chrony is using the public pool; no Sync Now needed.
   - **no public NTP available** — venue offline; **Sync Now** appears.
5. **Sync Now** sets Net Time from **this PC’s** date/time (browser ISO-8601 → `POST /sync`).

## Smoke checks

```bash
curl http://<IP>:8720/health
curl -H "Authorization: Bearer <token>" http://<IP>:8720/status
pct enter <CTID>
systemctl status net-time chrony
chronyc tracking
chronyc sources
```

Expect `/health` → `"status":"ok"`. `/status` → `public_ntp` of `reachable` or `unavailable`.
