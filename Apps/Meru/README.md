# Meru

Local LLM / interactive story agent surface for Alleycat events.

**Code:** `meru`  
**Path:** `Apps/Meru/`  
**Status: not shipped** — empty `HA_Component` scaffold only (`custom_components/` + `www/`). No integration code, MQTT topics, or Core Configurator keys yet.

Planned HA domain: `meru` (see [`Docs/Design Terms.md`](../../Docs/Design%20Terms.md)).

## Syntax

Stable identity strings for Ctrl+F rename / debug. Prefer changing the named
constant, then searching for leftover literals.

When you rename an identity string, update this section and `const.py` in the same PR.

### Rename blast radius

| Change this | Also touches |
| --- | --- |
| `DOMAIN` / folder / www path | manifest, panels, `/local/…`, entity_id prefixes (once shipped) |

### Identity checklist

| Kind | Exact string | Constant / source |
| --- | --- | --- |
| Domain (planned) | `meru` | Planned `const.py` `DOMAIN` — not present yet |
| MQTT / CC keys | — | None yet |
