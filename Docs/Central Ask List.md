# Central Server ask-list (Mission Control)

Revised after Central’s Oct 2026 ship (`GET /events`, `GET /game-state`, JSON `POST /players`, `PATCH /players`, teams, scoring / delayed-scores).

## Already covered — no action needed

- JSON `POST /players` + `PlayerResponse` body (incl. `pdn_code`, `email`, `team_*`, `active`)
- `GET /events`
- Active event via `GET /game-state`
- `PATCH /players/{id}` (name / email / team_id / active)
- Teams under `/events/{id}/teams`
- Soft inactive via `active` (no hard DELETE required)
- Scoring + delayed-scores PUTs

## When you’re ready

1. **Affiliation management JSON API** (ADR 0006) — categories / affiliations / player assignment so Registration can restore NeoCorp/Faction-style desk fields.
2. **Hours of operation** API — if Game Master should drive venue open/close windows.
3. **Special-event trigger** API — if operators should fire named gameplay specials from Game Master.

## Not requesting

- Hard `DELETE /players`
- Form-urlencoded player create
- Separate `GET /events/active` (we use `game-state`)
- Restored fixed `mode` enum (we use teams)
