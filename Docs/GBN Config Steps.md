# Galactic Bounty Network — Config Steps

Proxmox poster server + Home Assistant integration for capture and display.

Prerequisites:
- Master Control Server running (Phase 4) — GBN overlays Player from MCS
- Core Configurator with key `gbn` (URL) and MCS URL + token already set
- Shared HA Helpers on HA

App README: [`Apps/Galactic_Bounty_Network/README.md`](../Apps/Galactic_Bounty_Network/README.md)

---

## A. Proxmox LXC (poster server)

Copy `ProxmoxInstallFiles/install-gbn-proxmox.sh` to `/root/` on the Proxmox host, then on the **node** shell:

```bash
bash install-gbn-proxmox.sh
# or with local source:
# GBN_SRC=/path/to/Apps/Galactic_Bounty_Network/Server_Component \
# GBN_MCS_BASE=http://<mcs-ip>:8700 GBN_MCS_TOKEN=<token> \
# bash install-gbn-proxmox.sh
```

Confirm:

```bash
curl -s http://<gbn-ip>:8100/health
# {"status":"ok","service":"gbn"}
```

Set **Core Configurator → Galactic Bounty Network** to `http://<gbn-ip>:8100`.

Env file on the guest: `/etc/gbn.env` (`GBN_PUBLIC_BASE`, `GBN_MCS_BASE`, `GBN_MCS_TOKEN`).

---

## B. Home Assistant integration + panel

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Galactic_Bounty_Network\HA_Component\custom_components\gbn" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Galactic_Bounty_Network\HA_Component\www\gbn" root@<HA-IP>:/config/www/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Registration\HA_Component\www\registration" root@<HA-IP>:/config/www/
```

Merge from [`HomeAssist/configuration.yaml`](../HomeAssist/configuration.yaml):

- `gbn: {}`
- `panel_custom` entry for `gbn-panel`

Restart HA.

1. Settings → Devices & services → Add **Galactic Bounty Network** (install-only).
2. Sidebar **Galactic Bounty Network**: pick a Registration roster player → Generate → record/upload → create poster.
3. Open `/poster/player/{id}` on the GBN public URL (or via the success link).
4. Registration table **Poster** column shows thumb + open link (via HA proxy).

Panel API traffic goes through `/api/gbn/proxy/...` only — no browser LAN fetch.

---

## C. Active-players kiosk (optional)

Game server:

```bash
curl -X POST http://<gbn-ip>:8100/api/active-players \
  -H "Content-Type: application/json" \
  -d '{"player_ids":["12","34"],"interval_sec":30}'
```

Display machine: open `http://<gbn-ip>:8100/active-players`.

---

## D. Smoke checklist

- [ ] `/health` returns `service: gbn`
- [ ] Create poster in HA panel for a known MCS player
- [ ] Change player name in Registration → reload poster page → name updates (MCS overlay)
- [ ] `GET /api/players/{id}` on GBN returns **404** (removed)
- [ ] Registration Poster column shows thumb after create
- [ ] Core Configurator is the only place the GBN URL is stored
