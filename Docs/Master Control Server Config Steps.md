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

1. Seed or edit Core Configurator with MCS URL + token (and Central primary/secondary URLs).
2. Deploy Registration + Shared HA Helpers + Core Configurator to HA — see [`Home Assistant Config Steps.md`](Home%20Assistant%20Config%20Steps.md#deploy-mission-control-files-onto-ha) and [`File Structure.md` — On Home Assistant](File%20Structure.md#on-home-assistant).
3. Add the Registration integration (install-only — no token form). Registration pushes Central URLs to MCS via `POST /config` and polls `GET /players`.
4. Operators register / update / delete players from the Registration panel; HA services call MCS `POST` / `PUT` / `DELETE /players`. MCS maps canonical fields (`neocorp`, `role`) to Central legacy keys (`allegiance`, `hunter`).

## Updating MCS code later

Copy updated `Server_Component` files to the **Proxmox host** first, then into the LXC (CT id from install output, often `102`):

```powershell
# From your PC — replace <PROXMOX-IP>
scp "z:\CodingProjects\Alleycat\MissionControl\Apps\Master_Control_Server\Server_Component\player_normalize.py" root@<PROXMOX-IP>:/root/
scp "z:\CodingProjects\Alleycat\MissionControl\Apps\Master_Control_Server\Server_Component\central_client.py" root@<PROXMOX-IP>:/root/
scp "z:\CodingProjects\Alleycat\MissionControl\Apps\Master_Control_Server\Server_Component\models.py" root@<PROXMOX-IP>:/root/
scp "z:\CodingProjects\Alleycat\MissionControl\Apps\Master_Control_Server\Server_Component\main.py" root@<PROXMOX-IP>:/root/
```

On the Proxmox **host** shell (`pct` does not exist inside the LXC):

```bash
ls -la /root/*.py   # confirm files landed before push
pct push 102 /root/player_normalize.py /opt/mcs/player_normalize.py
pct push 102 /root/central_client.py /opt/mcs/central_client.py
pct push 102 /root/models.py /opt/mcs/models.py
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
