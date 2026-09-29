# Mission Control panel kit (Lit + TypeScript)

Source for the shared McPanel Lit base and every `panel_custom` sidebar module.
HAOS never runs Node — build on a workstation, deploy the static `www/` outputs.

## Build

```bash
cd Libraries/Shared_HA_Helpers/panel_kit
npm install
npm run build
```

Outputs:

| Bundle | Deploy path |
|---|---|
| `mc-panel.js` | `Libraries/.../www/shared_libraries/mc-panel.js` → `/config/www/shared_libraries/` |
| Feature panels | Each app’s `HA_Component/www/<app>/` → `/config/www/<app>/` |

`mc-panel.js` embeds Lit once and exposes `window.McPanel` (`Base`, `tokens`, `html`, `css`, `nothing`). Feature panels must not import `lit`; they extend `window.McPanel.Base`.

## Source layout

- `src/mc-panel/` — typed Lit McPanelBase + tokens + Alleycat shared chrome
- `src/panels/` — TypeScript sources for all Mission Control panels
