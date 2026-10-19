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
| `/opt/gbn/data/events/{event_id}/meta.json` | Display name for that Event (Event media card) |
| `/opt/gbn/data/active_event.json` | Last-known active Event (kiosk cache; Registration push + MCS) |
| `/opt/gbn/media/events/{event_id}/videos/{player_id}.*` | Capture clips per Event |
| `/opt/gbn/data/poster_templates.json` | Chrome templates (auto-seeded hunter/bounty) |
| `/opt/gbn/data/posters.json` | Legacy global poster store (opt-in via `?include_legacy=true` only) |
| `/opt/gbn/app/` | Python package (`uvicorn app.main:app`) |

**MCS on the guest is required for live Player overlays** and is the backup path for active Event. Set both in `/etc/gbn.env` to the same MCS URL/token as Core Configurator. Registration also pushes active Event to GBN (`PUT /api/events/active`) whenever operators set active — that is what keeps AlleycatTV `/poster-cycle` working after restarts without opening the page in a desktop browser.

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
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Registration\HA_Component\custom_components\registration" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Registration\HA_Component\www\registration" root@<HA-IP>:/config/www/
```

Merge from [`HomeAssist/configuration.yaml`](../HomeAssist/configuration.yaml):

- `gbn: {}`
- `panel_custom` entry for `gbn-panel`

Restart HA (Registration custom component change needs a restart). Hard-refresh the browser after updating `www/gbn/` / `www/registration/`.

1. Settings → Devices & services → Add **Galactic Bounty Network** (install-only).
2. In **Registration**, set an **active Event** before capture — this also pushes the Event id/name to GBN for AlleycatTV kiosks.
3. Sidebar **Galactic Bounty Network**: confirm the active-event chip → pick a Registration roster player → Generate → record/upload → create poster.
4. **Subject:** affiliation control is labeled **Allegiance/NeoCorp** (same values as before).
5. **Poster copy** + **Customize poster look:**
   - Hunter / Bounty: look section starts collapsed (auto-selected built-in).
   - Other roles: look section starts open — pick a template, or edit chrome and **Save as new template** before Create (Create does **not** auto-save templates).
   - Chrome is snapshotted onto the poster at create time.
6. **Event media** card: shows **Event name** (e.g. Development Event) with UUID muted; clip counts / sizes; **Export clips** (zip of `{player_id}.*` only); **Delete** an event’s media + posters.
7. Open `/poster/player/{id}` on the GBN public URL (or via the success link). The path stays player-scoped; GBN resolves the clip against the **active Event** on disk (`media/events/{event_id}/videos/…`).
8. Registration table **Poster** column shows thumb + open link for the active Event (via HA proxy).

Panel API traffic goes through `/api/gbn/proxy/...` only — no browser LAN fetch.

Templates API (proxied): `GET/POST /api/gbn/proxy/api/poster-templates`.  
Event media (proxied): `GET /api/gbn/proxy/api/events/media?ensure_event_id=&ensure_event_name=`, export/delete under `/api/events/{id}/…`.  
Active Event (proxied): `GET/PUT /api/gbn/proxy/api/events/active`.

---

## C. Poster display URLs

| URL | Purpose |
|---|---|
| `http://<gbn-ip>:8100/poster/player/{id}` | Single poster (resolved against active Event) |
| `http://<gbn-ip>:8100/poster-cycle` | **Active-event** posters only, rotate every 30s (AlleycatTV Content **+ Poster cycle**) |
| `http://<gbn-ip>:8100/poster-cycle?interval=45` | Same, custom interval (5–300s) |
| `http://<gbn-ip>:8100/active-players` | Game-server curated player list only |

### Poster cycle (AlleycatTV)

In AlleycatTV Content, **+ Poster cycle** adds `{gbn}/poster-cycle` as a webpage playlist item (1 hour slot). The GBN page:

1. `GET /api/events/active` (MCS → else `data/active_event.json` cache from Registration push)
2. `GET /api/posters?event_id=…` for that Event only (never the legacy global store)
3. Rotates every 30s; re-fetches the list every 15s

HUD shows Event name + poster count, or `NO ACTIVE EVENT` / `NO POSTERS FOR EVENT` when empty.

**Active Event sources (in order):** MCS `GET /events/active` when `GBN_MCS_*` works; otherwise GBN disk cache. Registration **set active event**, create-with-set-active, and HA restore-on-start all `PUT /api/events/active` on GBN so AlleycatTV Pis do not need a desktop browser visit to “wake” the cycle after a GBN restart.

Ops fallback (`/manage`): paste `http://<gbn-ip>:8100/poster-cycle` via **+ Poster cycle**.

Quick checks (use `curl.exe` on Windows PowerShell — bare `curl` is an alias):

```powershell
curl.exe -sS "http://<gbn-ip>:8100/api/events/active"
curl.exe -sS "http://<gbn-ip>:8100/api/posters"
curl.exe -sS "http://<gbn-ip>:8100/poster-cycle" | Select-Object -First 5
```

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
- [ ] `/etc/gbn.env` has `GBN_MCS_BASE` + `GBN_MCS_TOKEN` matching Core Configurator MCS
- [ ] Active event set in Registration; `GET /api/events/active` returns that id/name (`source` may be `registration`, `mcs`, or `gbn_cache`)
- [ ] GBN panel shows active-event chip; Event media shows **Event name** (not only UUID) with ACTIVE badge
- [ ] Create poster in HA panel for a known MCS player (clips land under `media/events/{id}/videos/`)
- [ ] Hunter / Bounty auto-select built-in templates; neither-role player Save as new before Create, then see the custom template in the dropdown
- [ ] Custom headline / amount / list labels appear on `/poster/player/{id}`
- [ ] Event media: sizes refresh, Export clips downloads a zip, Delete removes that event folder
- [ ] Change player name in Registration → reload poster page → name updates (MCS overlay)
- [ ] `GET /api/players/{id}` on GBN returns **404** (removed)
- [ ] Registration Poster column shows thumb after create (active Event only)
- [ ] Core Configurator is the only place the GBN URL is stored
- [ ] After a CT IP change, updating Core Configurator `gbn` is enough for new poster live links
- [ ] Desktop browser: `/poster-cycle` rotates active-event posters (HUD shows Event name)
- [ ] After `systemctl restart gbn`, set active in Registration once → Pi `/poster-cycle` recovers without a desktop visit
- [ ] AlleycatTV Content **+ Poster cycle** adds the GBN cycle URL to a broadcast group; Pi shows the same posters
