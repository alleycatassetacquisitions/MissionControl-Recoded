# Master Control Server Config Steps

Deploy the Master Control Server (MCS) as a Proxmox LXC. MCS is the only Central HTTP adapter. Home Assistant Registration talks to MCS; HA never talks to Central directly.

This assumes you are using **Proxmox**. Prefer the installer script below so someone with little experience can stand up MCS the same way as Home Assistant OS.

## Install

Run this on the **Proxmox node shell** (Datacenter → the host → **Shell**). Do not open a guest console.

1. Copy `ProxmoxInstallFiles/install-mcs-proxmox.sh` onto the Proxmox host as `/root/install-mcs-proxmox.sh` (USB, SCP, or paste into `nano`).
2. Make it executable and run:

```bash
chmod +x /root/install-mcs-proxmox.sh
bash /root/install-mcs-proxmox.sh
```

3. Wait for `Done. CT … is ready.` The script prints:
   - CTID and LAN IP
   - Console login: `root` / `alleycat` (override with `ROOT_PASSWORD=…`)
   - `http://<IP>:8700/health`
   - The generated API token

4. Put those two values into Home Assistant:

| Secret / Core Configurator field | Value |
| --- | --- |
| `cc_master_control_server` | `http://<printed-IP>:8700` |
| `cc_master_control_server_token` | the printed token |

Use [`HomeAssist/secrets.yaml.example`](../HomeAssist/secrets.yaml.example) on first CC seed, or the Core Configurator sidebar after the entry exists.

5. Confirm health from any PC on the LAN:

```bash
curl http://<printed-IP>:8700/health
```

Expect JSON with `"status":"ok"`.

The script defaults to **Ubuntu 24.04** standard, 1 core, 1 GB RAM, 8 GB disk on `local-lvm`, bridge `vmbr0`. If the Ubuntu template is not cached, it downloads it with `pveam`.

## Optional overrides

| Variable | Default | Purpose |
| --- | --- | --- |
| `CTID` | next free | Container ID |
| `STORAGE` | `local-lvm` | Root disk storage |
| `TEMPLATE_STORAGE` | `local` | Where LXC templates live |
| `TEMPLATE` | `ubuntu-24.04-standard` | Template name prefix |
| `BRIDGE` | `vmbr0` | Network bridge |
| `MCS_API_TOKEN` | random | Skip generation; use a known token |
| `MCS_SRC` | _(empty)_ | Host path to `Server_Component` to copy instead of git clone |
| `REPO_URL` | `https://github.com/alleycatassetacquisitions/MissionControl-Recoded.git` | Clone source when `MCS_SRC` is unset (needs network; private repos need a token or use `MCS_SRC` instead) |
| `ROOT_PASSWORD` | `alleycat` | LXC console / SSH root password (Mission Control default for all companion LXCs) |
| `SKIP_CONFIRM` | `0` | Set `1` to skip the 5-second cancel window |

Example with a local checkout already on the Proxmox host (**recommended** — no GitHub login):

```bash
MCS_SRC=/root/MissionControl/Apps/Master_Control_Server/Server_Component \
  bash /root/install-mcs-proxmox.sh
```

If the GitHub repo is **private**, `git clone` will ask for a username/password (use a [personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) as the password). Prefer `MCS_SRC` for venue deploys so volunteers never need GitHub credentials.

## After install

1. Seed or edit Core Configurator with MCS URL + token (and Central primary/secondary URLs). Secondary may be empty when there is no LAN mirror — do not leave a dead IP.
2. Deploy Registration + Shared HA Helpers + Core Configurator to HA — see [`Home Assistant Config Steps.md`](Home%20Assistant%20Config%20Steps.md#deploy-mission-control-files-onto-ha) and [`File Structure.md` — On Home Assistant](File%20Structure.md#on-home-assistant). Prefer `RESUME=ha-deploy` from the [venue installer](Venue%20Install.md) when updating a live site.
3. Add the Registration integration (install-only — no token form). Registration pushes Central URLs **plus** a venue peer snapshot to MCS via `POST /config` on setup, on `registration.sync_now`, and whenever Core Configurator Save changes MCS/Central/GBN/Net Time/AlleycatTV/Proxmox. MCS fans out companion `POST /config` to GBN and Net Time (soft-fail; MCS still returns 204). Inspect with Bearer `GET /config/status`. AlleycatTV HA publishes retained Pi `config` over MQTT separately. Registration polls `GET /players`.
4. Operators create/activate an **event**, then register players (name + optional email + tags) from the Registration panel. MCS proxies Central JSON create/PATCH and soft-deactivates via `active: false`. Use **Game Master** for scoring live/off, delayed scores, and affiliation catalog CRUD. Bug Buster reads Central crash logs via MCS `GET /device-logs`.

### Peer push / fan-out smoke test (on Proxmox host)

Replace the URLs with this venue’s Core Configurator values (empty secondary is valid):

```bash
TOKEN=$(pct exec 102 -- bash -lc "grep ^MCS_API_TOKEN= /etc/mcs.env | cut -d= -f2-")
pct exec 102 -- curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8700/config \
  -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \
  -d "{\"central_primary\":\"https://<central>\",\"central_secondary\":\"\",\"mcs_url\":\"http://<mcs-ip>:8700\",\"gbn_url\":\"http://<gbn-ip>:8100\",\"host_clock_url\":\"http://<proxmox-ip>:8721\"}"
pct exec 102 -- curl -s -H "Authorization: Bearer ${TOKEN}" http://127.0.0.1:8700/config/status
pct exec 101 -- journalctl -u gbn -n 20 --no-pager --since '1 min ago' | grep -iE 'GBN /config|POST /config' || true
```

`last_fanout.gbn.ok` should be true and GBN should log `GBN /config applied` from the MCS IP. Day-2 pushes come from Registration (CC Save / `sync_now`), not these curls.

For a full code push + optional smoke from Windows, see [`ProxmoxInstallFiles/push-peer-hub-from-pc.ps1`](../ProxmoxInstallFiles/push-peer-hub-from-pc.ps1) and [`push-peer-hub-venue.sh`](../ProxmoxInstallFiles/push-peer-hub-venue.sh).

## Updating MCS code later

Prefer a **flat** `Server_Component` tree as `SRC` (files at top level — not nested `Server_Component/Server_Component/`). Windows `scp -r Server_Component` often nests; stage contents then use the push helper:

```powershell
# From your PC — replace <PROXMOX-IP>; stage flat tree on host
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Master_Control_Server\Server_Component\*" root@<PROXMOX-IP>:/root/mcs-src/
scp "z:\CodingProjects\Alleycat\MissionControl\ProxmoxInstallFiles\lib\push-server-component.sh" root@<PROXMOX-IP>:/root/
scp "z:\CodingProjects\Alleycat\MissionControl\ProxmoxInstallFiles\push-peer-hub-venue.sh" root@<PROXMOX-IP>:/root/
```

On the Proxmox **host** shell:

```bash
# Confirm flat: main.py at top of SRC
ls /root/mcs-src/main.py
CTID=102 UNIT=mcs DEST=/opt/mcs SRC=/root/mcs-src bash /root/push-server-component.sh
# or: bash /root/push-peer-hub-venue.sh   # MCS + GBN together
```

Per-file `pct push` still works for hotfixes:

```bash
pct push 102 /root/main.py /opt/mcs/main.py
pct exec 102 -- systemctl restart mcs
```

## Container resources


| Setting | Value |
| --- | --- |
| CPU | 1 core |
| RAM | 1 GB |
| Disk | 8 GB |
| OS | Ubuntu 24.04 LXC |
| Port | 8700 |
| Root password | `alleycat` (default for Mission Control LXCs) |


## Dev / test without the script

You may still create an LXC by hand and run uvicorn for testing. Production and volunteer deploys should use `install-mcs-proxmox.sh`.
