# Master Control Server Config Steps

Deploy the Master Control Server (MCS) as a Proxmox LXC. MCS is the only Central HTTP adapter. Home Assistant Registration talks to MCS; HA never talks to Central directly.

This assumes you are using **Proxmox**. Prefer the installer script below so someone with little experience can stand up MCS the same way as Home Assistant OS.

## Install

Run this on the **Proxmox node shell** (Datacenter → the host → **Shell**). Do not open a guest console.

1. Copy `Docs/install-mcs-proxmox.sh` onto the Proxmox host as `/root/install-mcs-proxmox.sh` (USB, SCP, or paste into `nano`).
2. Make it executable and run:

```bash
chmod +x /root/install-mcs-proxmox.sh
bash /root/install-mcs-proxmox.sh
```

3. Wait for `Done. CT … is ready.` The script prints:
   - CTID and LAN IP
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
| `REPO_URL` | MissionControl GitHub | Clone source when `MCS_SRC` is unset |
| `SKIP_CONFIRM` | `0` | Set `1` to skip the 5-second cancel window |

Example with a local checkout already on the Proxmox host:

```bash
MCS_SRC=/root/MissionControl/Apps/Master_Control_Server/Server_Component \
  bash /root/install-mcs-proxmox.sh
```

## After install

1. Seed or edit Core Configurator with MCS URL + token (and Central primary/secondary URLs).
2. Deploy Registration + Shared HA Helpers to HA (see deployment plan).
3. Add the Registration integration (install-only — no token form). Registration pushes Central URLs to MCS and polls `/players`.

## Container resources


| Setting | Value |
| --- | --- |
| CPU | 1 core |
| RAM | 1 GB |
| Disk | 8 GB |
| OS | Ubuntu 24.04 LXC |
| Port | 8700 |


## Dev / test without the script

You may still create an LXC by hand and run uvicorn for testing. Production and volunteer deploys should use `install-mcs-proxmox.sh`.
