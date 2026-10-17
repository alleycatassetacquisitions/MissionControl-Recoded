# Game Master

Sidebar panel for **gameplay** controls: live scoring, delayed scores, and (later) hours of operation / special events.

**Registration** owns event create / set-active and player registration. Game Master reads the active event from Central `GET /game-state` via MCS and does not change which event is selected.

## Architecture

```
Game Master panel → HA websocket → MCS → Alleycat Central
```

| MCS route | Central |
|---|---|
| `GET /game-state` | `GET /game-state` |
| `PUT /scoring` | `PUT /events/{active}/scoring` |
| `PUT /delayed-scores` | `PUT /events/{active}/delayed-scores` |

## Install

1. Deploy `HA_Component/custom_components/game_master/` and `www/game_master/`.
2. Add to HA `configuration.yaml`:

```yaml
game_master: {}

panel_custom:
  - name: game-master-panel
    sidebar_title: Game Master
    sidebar_icon: mdi:crown
    url_path: game-master
    module_url: /local/game_master/game-master-panel.js
```

3. Ensure Core Configurator has MCS URL + Bearer token.
4. Restart HA; add the Game Master integration once (or rely on YAML import).

## Gated until Central ships

- Hours of operation
- Special-event triggers
