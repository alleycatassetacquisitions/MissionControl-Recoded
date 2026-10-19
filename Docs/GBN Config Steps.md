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

curl -s http://<gbn-ip>:8100/api/poster-templates
# JSON array including builtin hunter + bounty
```

Set **Core Configurator → Galactic Bounty Network** to `http://<gbn-ip>:8100`.

When the CT gets a new LAN IP, update Core Configurator to that URL — poster “live” links and API `poster_url` / `video_url` follow the request Host (no LXC rebuild). Optionally refresh `GBN_PUBLIC_BASE` in `/etc/gbn.env` as a fallback; `GBN_MCS_BASE` / `GBN_MCS_TOKEN` still live there.

Env file on the guest: `/etc/gbn.env` (`GBN_PUBLIC_BASE`, `GBN_MCS_BASE`, `GBN_MCS_TOKEN`, optional `GBN_TEMPLATES`).

Data on the guest:

| Path | Purpose |
| --- | --- |
| `/opt/gbn/data/events/{event_id}/posters.json` | Poster metadata per Event |
| `/opt/gbn/media/events/{event_id}/videos/{player_id}.*` | Capture clips per Event |
| `/opt/gbn/data/poster_templates.json` | Chrome templates (auto-seeded hunter/bounty) |
| `/opt/gbn/data/posters.json` | Legacy global poster store (read fallback) |
| `/opt/gbn/app/` | Python package (`uvicorn app.main:app`) |

### Upgrade app on an existing CT

From a workstation (example IPs: Proxmox `10.10.50.205`, GBN CT `101`):

```powershell
ssh root@<PROXMOX-IP> "rm -rf /tmp/gbn-app && mkdir -p /tmp/gbn-app"
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Galactic_Bounty_Network\Server_Component\app\*" root@<PROXMOX-IP>:/tmp/gbn-app/
```

On the Proxmox host — **confirm new files before installing**:

```bash
ls -la /tmp/gbn-app/template_store.py /tmp/gbn-app/routers/templates.py
# both must exist

pct exec <CTID> -- mkdir -p /opt/gbn/app
tar -C /tmp/gbn-app -cf - . | pct exec <CTID> -- tar -C /opt/gbn/app -xf -
pct exec <CTID> -- bash -lc '
  chown -R gbn:gbn /opt/gbn/app
  systemctl restart gbn
  sleep 2
  curl -s http://127.0.0.1:8100/api/poster-templates
'
```

A stale `/tmp/gbn-app` without `templates.py` / `template_store.py` leaves the service on old routes (`404` on `/api/poster-templates`).

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

Restart HA. Hard-refresh the browser after updating `www/gbn/`.

1. Settings → Devices & services → Add **Galactic Bounty Network** (install-only).
2. In **Registration**, set an **active Event** before capture (roster + clip folders follow that event).
3. Sidebar **Galactic Bounty Network**: confirm the active-event chip → pick a Registration roster player → Generate → record/upload → create poster.
4. **Subject:** affiliation control is labeled **Allegiance/NeoCorp** (same values as before).
5. **Poster copy** + **Customize poster look:**
   - Hunter / Bounty: look section starts collapsed (auto-selected built-in).
   - Other roles: look section starts open — pick a template, or edit chrome and **Save as new template** before Create (Create does **not** auto-save templates).
   - Chrome is snapshotted onto the poster at create time.
6. **Event media** card: see clip counts / sizes, **Export clips** (zip of `{player_id}.*` only), or **Delete** an event’s media + posters.
7. Open `/poster/player/{id}` on the GBN public URL (or via the success link).
8. Registration table **Poster** column shows thumb + open link (via HA proxy).

Panel API traffic goes through `/api/gbn/proxy/...` only — no browser LAN fetch.

Templates API (proxied): `GET/POST /api/gbn/proxy/api/poster-templates`.  
Event media (proxied): `GET /api/gbn/proxy/api/events/media`, export/delete under `/api/events/{id}/…`.

---

## C. Poster display URLs

| URL | Purpose |
|---|---|
| `http://<gbn-ip>:8100/poster/player/{id}` | Single poster |
| `http://<gbn-ip>:8100/poster-cycle` | All made posters, rotate every 30s (AlleycatTV Content **+ Poster cycle**) |
| `http://<gbn-ip>:8100/poster-cycle?interval=45` | Same, custom interval (5–300s) |
| `http://<gbn-ip>:8100/active-players` | Game-server curated player list only |

### Poster cycle (AlleycatTV)

In AlleycatTV Content, **+ Poster cycle** adds `{gbn}/poster-cycle` as a webpage playlist item (1 hour slot). The GBN page loads `GET /api/events/active` then `GET /api/posters?event_id=…` and rotates **that event’s** posters inside Chromium.

Registration **set active event** (and HA restore-on-start) also `PUT /api/events/active` on GBN so kiosks do not depend on a browser visit to seed the active-event cache. Confirm `GBN_MCS_BASE` / `GBN_MCS_TOKEN` in `/etc/gbn.env` as a backup path.

Ops fallback (`/manage`): paste `http://<gbn-ip>:8100/poster-cycle` via **+ Poster cycle**.

### Active-players kiosk (optional)

Game server:

```bash
curl -X POST http://<gbn-ip>:8100/api/active-players \
  -H "Content-Type: application/json" \
  -d '{"player_ids":["12","34"],"interval_sec":30}'
```

Display machine: open `http://<gbn-ip>:8100/active-players` (iframe paths are same-origin relative — survive IP changes).

---

## D. Smoke checklist

- [ ] `/health` returns `service: gbn`
- [ ] `GET /api/poster-templates` returns hunter + bounty built-ins (not 404)
- [ ] Active event set in Registration; GBN panel shows active-event chip
- [ ] Create poster in HA panel for a known MCS player (clips land under `media/events/{id}/videos/`)
- [ ] Hunter / Bounty auto-select built-in templates; neither-role player Save as new before Create, then see the custom template in the dropdown
- [ ] Custom headline / amount / list labels appear on `/poster/player/{id}`
- [ ] Event media: sizes refresh, Export clips downloads a zip, Delete removes that event folder
- [ ] Change player name in Registration → reload poster page → name updates (MCS overlay)
- [ ] `GET /api/players/{id}` on GBN returns **404** (removed)
- [ ] Registration Poster column shows thumb after create
- [ ] Core Configurator is the only place the GBN URL is stored
- [ ] After a CT IP change, updating Core Configurator `gbn` is enough for new poster live links
- [ ] `/poster-cycle` returns HTML and rotates posters when more than one exists
- [ ] AlleycatTV Content **+ Poster cycle** adds the GBN cycle URL to a broadcast group
