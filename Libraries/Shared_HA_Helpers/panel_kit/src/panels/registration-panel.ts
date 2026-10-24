/// <reference path="../mc-panel/globals.d.ts" />
/**
 * Registration panel — events + player roster via MCS.
 *
 * Design contract:
 *  - Extends McPanelBase from shared_libraries/mc-panel.js.
 *  - ALL data reads and writes go through hass.callWS / hass.callService.
 *    Zero direct fetch() calls to MCS or any LAN IP.
 *
 * Websocket:
 *  - registration/get_roster
 *  - registration/get_events
 *  - registration/get_active_event
 *  - registration/get_teams
 *  - game_master/get_affiliation_catalog (read-only; catalog CRUD lives in Game Master)
 *
 * HA services:
 *  - registration.sync_now
 *  - registration.register_player (name + email + affiliations)
 *  - registration.create_event / update_event / set_active_event
 *  - registration.update_player / delete_player (soft-deactivate)
 *
 * Affiliations: dropdowns (one selection per category). Faction allows
 * create-on-type via Game Master. Roster table still shows tag chips.
 * Categories/choices/defaults are managed in Game Master (HA-only defaults).
 */

import {
  AffCatalog,
  AffCategory,
  PlayerAffiliation,
  buildAffiliationsPayload,
  defaultsByCategoryId,
  emptyCatalog,
  ensureAffiliationChoice,
  filterChoices,
  findChoiceExact,
  isFactionCategory,
  playerAssignmentForCategory,
} from "../shared/affiliations";

const PLAYER_NAME_MAX = 32;

type RegPlayer = {
  id?: string | number;
  name?: string;
  pdn_code?: string;
  mode?: string;
  role?: string;
  created_at?: string;
  email?: string;
  team_id?: string | null;
  team_name?: string;
  active?: boolean;
  event_id?: string | null;
  affiliations?: PlayerAffiliation[];
  neocorp?: string;
  faction?: string;
};

type RegEvent = {
  id?: string;
  name?: string;
  venue_name?: string | null;
  created_at?: string;
};

type RegTeam = {
  id?: string;
  event_id?: string;
  name?: string;
};

type RegPoster = {
  player_id?: string;
  poster_url?: string;
  video_url?: string;
};

class RegistrationPanel extends window.McPanel.Base {
  static get properties() {
    return {
      ...super.properties,
      _roster: { state: true },
      _postersByPlayer: { state: true },
      _search: { state: true },
      _nameStatus: { state: true },
      _fName: { state: true },
      _fEmail: { state: true },
      _highlightName: { state: true },
      _events: { state: true },
      _eventsReady: { state: true },
      _eventsDetail: { state: true },
      _activeEventId: { state: true },
      _activeEvent: { state: true },
      _evMode: { state: true },
      _evCreateName: { state: true },
      _evCreateVenue: { state: true },
      _evCreateSetActive: { state: true },
      _evEditId: { state: true },
      _evEditName: { state: true },
      _evEditVenue: { state: true },
      _evSetActiveId: { state: true },
      _teams: { state: true },
      _catalog: { state: true },
      _fAffByCat: { state: true },
      _factionOpenId: { state: true },
      _editId: { state: true },
      _editTeamId: { state: true },
      _editActive: { state: true },
    };
  }

  declare _roster: RegPlayer[];
  declare _postersByPlayer: Record<string, RegPoster>;
  declare _search: string;
  declare _nameStatus: "" | "available" | "taken";
  declare _fName: string;
  declare _fEmail: string;
  declare _highlightName: string;
  declare _events: RegEvent[];
  declare _eventsReady: boolean;
  declare _eventsDetail: string;
  declare _activeEventId: string | null;
  declare _activeEvent: RegEvent | null;
  declare _evMode: "create" | "edit" | "set";
  declare _evCreateName: string;
  declare _evCreateVenue: string;
  declare _evCreateSetActive: boolean;
  declare _evEditId: string;
  declare _evEditName: string;
  declare _evEditVenue: string;
  declare _evSetActiveId: string;
  declare _teams: RegTeam[];
  declare _catalog: AffCatalog;
  declare _fAffByCat: Record<string, string>;
  declare _factionOpenId: string;
  declare _editId: string;
  declare _editTeamId: string;
  declare _editActive: boolean;

  private _checkTimer: ReturnType<typeof setTimeout> | null = null;
  private _factionBlurTimer: ReturnType<typeof setTimeout> | null = null;
  private _editPrevAff: Record<string, string> = {};

  constructor() {
    super();
    this._roster = [];
    this._postersByPlayer = {};
    this._search = "";
    this._nameStatus = "";
    this._fName = "";
    this._fEmail = "";
    this._highlightName = "";
    this._events = [];
    this._eventsReady = false;
    this._eventsDetail = "";
    this._activeEventId = null;
    this._activeEvent = null;
    this._evMode = "create";
    this._evCreateName = "";
    this._evCreateVenue = "";
    this._evCreateSetActive = true;
    this._evEditId = "";
    this._evEditName = "";
    this._evEditVenue = "";
    this._evSetActiveId = "";
    this._teams = [];
    this._catalog = emptyCatalog();
    this._fAffByCat = {};
    this._factionOpenId = "";
    this._editId = "";
    this._editTeamId = "";
    this._editActive = true;
  }

  static get styles() {
    const base = super.styles;
    const baseArr = Array.isArray(base) ? base : base ? [base] : [];
    return [
      ...baseArr,
      window.McPanel.css`
        :host {
          min-height: 100vh;
        }
        .wrap {
          max-width: none;
          margin: 0;
          padding: 0;
        }
        .page-header {
          display: block;
          padding: 18px 24px;
          margin-bottom: 0;
          border-bottom: 1px solid var(--divider-color, #1f3a44);
          background: var(--card-background-color, #10151c);
        }
        .header-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
        }
        .page-header h1 {
          margin: 0;
          font-size: 20px;
        }
        .name-hint {
          font-size: 12px;
          color: var(--secondary-text-color, #7aa8b8);
          margin: 2px 0 8px;
        }
        .aff-group {
          margin-bottom: 10px;
        }
        .aff-combo {
          position: relative;
        }
        .aff-combo-menu {
          position: absolute;
          z-index: 20;
          left: 0;
          right: 0;
          top: calc(100% + 2px);
          max-height: 220px;
          overflow-y: auto;
          margin: 0;
          padding: 4px 0;
          list-style: none;
          background: var(--secondary-background-color, #0d1418);
          border: 1px solid var(--divider-color, #1f3a44);
          border-radius: 6px;
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
        }
        .aff-combo-menu li {
          margin: 0;
          padding: 8px 12px;
          cursor: pointer;
          font-size: 14px;
          color: var(--primary-text-color, #e8f6ff);
        }
        .aff-combo-menu li:hover,
        .aff-combo-menu li.active {
          background: rgba(0, 229, 255, 0.12);
        }
        .aff-combo-menu li.create-hint {
          color: var(--secondary-text-color, #7aa8b8);
          font-size: 12px;
          cursor: default;
        }
        .aff-combo-menu li.create-hint:hover {
          background: transparent;
        }
        .chip-row {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .chip {
          margin: 0;
          padding: 5px 12px;
          background: transparent;
          color: var(--primary-color, #00e5ff);
          border: 1px solid var(--primary-color, #00e5ff);
          border-radius: 999px;
          font: inherit;
          font-size: 13px;
          cursor: pointer;
        }
        .chip:hover {
          background: rgba(0, 229, 255, 0.08);
        }
        .chip.active {
          background: var(--primary-color, #00e5ff);
          color: #041016;
          font-weight: 600;
        }
        .chip-static {
          display: inline-block;
          margin: 0 4px 4px 0;
          padding: 2px 10px;
          border: 1px solid var(--primary-color, #00e5ff);
          border-radius: 999px;
          font-size: 12px;
          white-space: nowrap;
        }
        .chip-static .chip-cat {
          color: var(--secondary-text-color, #7aa8b8);
          margin-right: 4px;
        }
        .aff-hint {
          font-size: 12px;
          color: var(--secondary-text-color, #7aa8b8);
          margin: 0;
        }
        .sub {
          color: var(--secondary-text-color, #7aa8b8);
          font-size: 13px;
          margin-top: 4px;
        }
        .events-block {
          min-width: 0;
          margin-bottom: 28px;
          padding-bottom: 24px;
          border-bottom: 1px solid var(--divider-color, #1f3a44);
        }
        .events-block .form-title {
          margin-bottom: 6px;
        }
        .active-line {
          font-size: 14px;
          margin: 0 0 10px;
        }
        .active-line strong {
          color: var(--primary-color, #00e5ff);
        }
        .events-gate {
          font-size: 13px;
          color: var(--secondary-text-color, #7aa8b8);
          margin: 0 0 12px;
        }
        .mode-toggle {
          display: flex;
          gap: 0;
          margin: 0 0 12px;
          border: 1px solid var(--primary-color, #00e5ff);
          border-radius: 6px;
          overflow: hidden;
        }
        .mode-toggle button {
          flex: 1;
          margin: 0;
          padding: 8px 10px;
          background: transparent;
          color: var(--primary-color, #00e5ff);
          border: 0;
          border-right: 1px solid var(--primary-color, #00e5ff);
          font: inherit;
          font-size: 12px;
          font-weight: 600;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          cursor: pointer;
        }
        .mode-toggle button:last-child {
          border-right: 0;
        }
        .mode-toggle button.active {
          background: var(--primary-color, #00e5ff);
          color: #041016;
        }
        .events-block label {
          display: block;
          font-size: 11px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: var(--secondary-text-color, #7aa8b8);
          margin: 8px 0 4px;
        }
        .events-block input,
        .events-block select {
          width: 100%;
          box-sizing: border-box;
          padding: 8px 10px;
          background: var(--secondary-background-color, #0d1418);
          color: var(--primary-text-color, #e8f6ff);
          border: 1px solid var(--divider-color, #1f3a44);
          border-radius: 6px;
          font: inherit;
        }
        .events-block label.check-row,
        .form-col label.check-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 10px;
          margin-bottom: 0;
          font-size: 13px;
          text-transform: none;
          letter-spacing: 0;
          color: var(--primary-text-color, #e8f6ff);
        }
        .events-block label.check-row input,
        .form-col label.check-row input {
          width: auto;
          flex-shrink: 0;
          margin: 0;
        }
        .events-block .btn-create,
        .events-block .btn-ghost {
          margin-top: 12px;
          width: 100%;
        }
        .layout {
          display: grid;
          grid-template-columns: 380px 1fr;
          min-height: calc(100vh - 100px);
        }
        .form-col,
        .table-col {
          padding: 20px 24px;
        }
        .form-col {
          border-right: 1px solid var(--divider-color, #1f3a44);
        }
        .form-title {
          margin: 0 0 8px;
          font-size: 16px;
          font-weight: 600;
          letter-spacing: 0.04em;
        }
        .form-col label {
          display: block;
          font-size: 12px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: var(--secondary-text-color, #7aa8b8);
          margin: 12px 0 6px;
        }
        .form-col input,
        .form-col select {
          width: 100%;
          box-sizing: border-box;
          padding: 10px 12px;
          background: var(--secondary-background-color, #0d1418);
          color: var(--primary-text-color, #e8f6ff);
          border: 1px solid var(--divider-color, #1f3a44);
          border-radius: 6px;
          font: inherit;
        }
        .form-actions {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 16px;
        }
        .form-actions .btn {
          margin-top: 0;
        }
        .btn-create {
          background: var(--primary-color, #00e5ff);
          color: #041016;
          border: 0;
          border-radius: 6px;
          padding: 10px 16px;
          font-weight: 600;
          cursor: pointer;
          font: inherit;
        }
        .btn-ghost {
          background: transparent;
          color: var(--primary-color, #00e5ff);
          border: 1px solid var(--primary-color, #00e5ff);
          border-radius: 6px;
          padding: 10px 16px;
          cursor: pointer;
          font: inherit;
        }
        .btn-create:disabled,
        .btn-ghost:disabled,
        .edit-btn:disabled,
        .delete-btn:disabled {
          opacity: 0.45;
          cursor: not-allowed;
        }
        .feedback {
          min-height: 20px;
          font-size: 13px;
          margin-top: 12px;
        }
        .feedback.kind-err {
          color: #e24b4a;
          font-weight: 600;
        }
        .search-row {
          margin-bottom: 14px;
        }
        .search-row input {
          width: 100%;
          box-sizing: border-box;
          padding: 8px 12px;
        }
        .roster-table {
          width: 100%;
          border-collapse: collapse;
        }
        .roster-table th,
        .roster-table td {
          text-align: left;
          padding: 10px 8px;
          border-bottom: 1px solid var(--divider-color, #1f3a44);
          font-size: 14px;
        }
        .roster-table th {
          font-size: 11px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--secondary-text-color, #7aa8b8);
        }
        .roster-table tr.highlight {
          background: rgba(0, 229, 255, 0.1);
          outline: 1px solid var(--primary-color, #00e5ff);
        }
        .empty {
          color: var(--secondary-text-color);
          text-align: center;
          padding: 32px;
        }
        .actions-cell {
          white-space: nowrap;
        }
        .edit-btn,
        .delete-btn {
          margin-top: 0;
          padding: 4px 10px;
          font-size: 12px;
          background: transparent;
          color: var(--primary-color, #00e5ff);
          border: 1px solid var(--primary-color, #00e5ff);
          border-radius: 4px;
          cursor: pointer;
          font: inherit;
        }
        .delete-btn {
          color: #e24b4a;
          border-color: #e24b4a;
          margin-left: 6px;
        }
        .poster-cell {
          min-width: 88px;
        }
        .poster-cell a {
          color: var(--primary-color, #00e5ff);
          text-decoration: none;
        }
        .poster-thumb {
          width: 56px;
          height: 32px;
          object-fit: cover;
          vertical-align: middle;
          border: 1px solid var(--divider-color, #1f3a44);
          margin-right: 6px;
          background: #000;
        }
        .poster-missing {
          color: var(--secondary-text-color);
          font-size: 0.8rem;
        }
        .name-status {
          min-height: 18px;
          font-size: 13px;
          margin-top: 6px;
        }
        .name-status.status-ok {
          color: #4cde97;
        }
        .name-status.status-err {
          color: #e24b4a;
        }
        @media (max-width: 900px) {
          .layout {
            grid-template-columns: 1fr;
          }
          .form-col {
            border-right: 0;
            border-bottom: 1px solid var(--divider-color, #1f3a44);
          }
        }
      `,
    ];
  }

  override disconnectedCallback(): void {
    if (this._checkTimer) {
      clearTimeout(this._checkTimer);
      this._checkTimer = null;
    }
    super.disconnectedCallback();
  }

  _token(): string {
    return (
      (this.hass as { auth?: { data?: { access_token?: string } } } | null)
        ?.auth?.data?.access_token || ""
    );
  }

  _formatErr(err: unknown): string {
    if (err == null) return "unknown error";
    if (typeof err === "string") return err;
    const e = err as {
      message?: string;
      error?: string | { message?: string };
      code?: string;
    };
    if (typeof e.error === "object" && e.error?.message) return e.error.message;
    if (typeof e.error === "string") return e.error;
    return e.message || e.code || JSON.stringify(err);
  }

  async _resolveAffiliationsPayload(
    selected: Record<string, string>,
    previous?: Record<string, string>
  ): Promise<Record<string, string | null>> {
    await this._loadCatalog();
    // Faction only: create missing typed choices via Game Master.
    for (const cat of this._catalog.categories || []) {
      if (!isFactionCategory(cat.name)) continue;
      const typed = (selected[cat.id] || "").trim();
      if (!typed) continue;
      if (findChoiceExact(cat.affiliations || [], typed)) continue;
      if (!this.hass) continue;
      await ensureAffiliationChoice(this.hass, cat.id, typed);
      await this._loadCatalog();
    }
    return buildAffiliationsPayload(
      this._catalog.categories || [],
      selected,
      { previousByCategoryId: previous }
    );
  }

  _formPayload() {
    const payload: {
      name: string;
      email?: string;
      affiliations?: Record<string, string | null>;
    } = {
      name: this._fName.trim(),
    };
    const email = this._fEmail.trim();
    if (email) payload.email = email;
    return payload;
  }

  /** Prefill create-mode affiliation dropdowns from HA catalog defaults. */
  _applyCreateDefaults() {
    this._fAffByCat = defaultsByCategoryId(this._catalog.categories || []);
  }

  _clearForm() {
    this._fName = "";
    this._fEmail = "";
    this._nameStatus = "";
    this._editId = "";
    this._editTeamId = "";
    this._editActive = true;
    this._editPrevAff = {};
    this._factionOpenId = "";
    this._applyCreateDefaults();
    if (this._checkTimer) {
      clearTimeout(this._checkTimer);
      this._checkTimer = null;
    }
    if (this._factionBlurTimer) {
      clearTimeout(this._factionBlurTimer);
      this._factionBlurTimer = null;
    }
  }

  _onNameInput(value: string) {
    this._fName = value.slice(0, PLAYER_NAME_MAX);
    if (this._checkTimer) clearTimeout(this._checkTimer);
    this._checkTimer = setTimeout(() => this._checkName(this._fName), 300);
  }

  _checkName(name: string) {
    const trimmed = name.trim();
    if (!trimmed) {
      this._nameStatus = "";
      return;
    }
    const needle = trimmed.toLowerCase();
    const editingId = this._editId ? String(this._editId) : "";
    const clash = this._roster.find(
      (p) =>
        (p.name || "").trim().toLowerCase() === needle &&
        (!editingId || String(p.id ?? "") !== editingId)
    );
    this._nameStatus = clash ? "taken" : "available";
  }

  _filteredRoster(): RegPlayer[] {
    const term = this._search.trim().toLowerCase();
    if (!term) return this._roster;
    return this._roster.filter(
      (p) =>
        String(p.id ?? "")
          .toLowerCase()
          .includes(term) ||
        String(p.name ?? "")
          .toLowerCase()
          .includes(term) ||
        String(p.pdn_code ?? "")
          .toLowerCase()
          .includes(term) ||
        String(p.email ?? "")
          .toLowerCase()
          .includes(term)
    );
  }

  _teamOf(p: RegPlayer): string {
    const name = (p.team_name || "").trim();
    if (name) return name;
    if (p.team_id) return String(p.team_id);
    return "Unassigned";
  }

  _activeOf(p: RegPlayer): string {
    return p.active === false ? "Inactive" : "Active";
  }

  _formatCreated(value?: string): string {
    if (!value) return "";
    try {
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return value;
      return d.toLocaleString();
    } catch {
      return value;
    }
  }

  _activeLabel(): string {
    const fromActive = (this._activeEvent?.name || "").trim();
    if (fromActive) return fromActive;
    if (this._activeEventId) {
      const cached = this._events.find(
        (e) => String(e.id) === String(this._activeEventId)
      );
      const fromCache = (cached?.name || "").trim();
      if (fromCache) return fromCache;
      // Last resort — UUID only when we truly have no name yet
      return this._activeEventId;
    }
    return "None — create or set an active event before registering players";
  }

  override async _boot() {
    await this._loadAll();
  }

  async _loadAll() {
    await Promise.all([
      this._loadRoster(),
      this._loadEvents(),
      this._loadActiveEvent(),
      this._loadPosters(),
    ]);
    await this._loadTeams();
    await this._loadCatalog();
  }

  async _loadTeams() {
    try {
      const result = await this.hass!.callWS<{
        teams?: RegTeam[];
        event_id?: string | null;
      }>({
        type: "registration/get_teams",
        event_id: this._activeEventId || undefined,
      });
      this._teams = result?.teams ?? [];
    } catch (_) {
      this._teams = [];
    }
  }

  async _loadCatalog() {
    const prevEvent = this._catalog?.event_id || null;
    try {
      const result = await this.hass!.callWS<AffCatalog>({
        type: "game_master/get_affiliation_catalog",
      });
      const next: AffCatalog = {
        event_id: result?.event_id ?? null,
        categories: result?.categories ?? [],
      };
      const eventChanged =
        Boolean(prevEvent) &&
        Boolean(next.event_id) &&
        String(prevEvent) !== String(next.event_id);
      this._catalog = next;
      if (eventChanged) {
        this._editPrevAff = {};
        if (!this._editId) this._applyCreateDefaults();
      } else if (!this._editId && Object.keys(this._fAffByCat).length === 0) {
        this._applyCreateDefaults();
      }
    } catch (_) {
      this._catalog = emptyCatalog();
    }
  }

  async _loadPosters() {
    this._postersByPlayer = {};
    try {
      const headers: Record<string, string> = { "cache-control": "no-store" };
      if (this._token()) headers.Authorization = `Bearer ${this._token()}`;
      const q = this._activeEventId
        ? `?event_id=${encodeURIComponent(this._activeEventId)}`
        : "";
      const resp = await fetch(`/api/gbn/proxy/api/posters${q}`, {
        headers,
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!resp.ok) return;
      const list = await resp.json();
      if (!Array.isArray(list)) return;
      const map: Record<string, RegPoster> = {};
      for (const p of list) {
        const id = String(p.player_id || "");
        if (id) map[id] = p;
      }
      this._postersByPlayer = map;
    } catch (_) {
      // GBN may not be installed yet — roster still works without posters.
    }
  }

  async _loadRoster() {
    try {
      const result = await this.hass!.callWS<{ players?: RegPlayer[] }>({
        type: "registration/get_roster",
      });
      this._roster = result?.players ?? [];
      if (this._fName.trim()) this._checkName(this._fName);
    } catch (err) {
      this._roster = [];
      this._feedback("Could not load roster: " + this._formatErr(err), "err");
    }
  }

  async _loadEvents() {
    try {
      const result = await this.hass!.callWS<{
        ready?: boolean;
        events?: RegEvent[];
        detail?: string | null;
      }>({ type: "registration/get_events" });
      this._events = result?.events ?? [];
      this._eventsReady = Boolean(result?.ready);
      this._eventsDetail = result?.detail || "";
    } catch (err) {
      this._events = [];
      this._eventsReady = false;
      this._eventsDetail = this._formatErr(err);
    }
  }

  async _loadActiveEvent() {
    try {
      const result = await this.hass!.callWS<{
        active_event_id?: string | null;
        event?: RegEvent | null;
      }>({ type: "registration/get_active_event" });
      this._activeEventId = result?.active_event_id ?? null;
      let event = result?.event ?? null;
      // Merge name from local events list if get-active only has the UUID
      if (
        event &&
        !(event.name || "").trim() &&
        this._activeEventId
      ) {
        const cached = this._events.find(
          (e) => String(e.id) === String(this._activeEventId)
        );
        if (cached?.name) {
          event = { ...event, name: cached.name, venue_name: cached.venue_name };
        }
      }
      this._activeEvent = event;
      if (this._activeEventId && !this._evSetActiveId) {
        this._evSetActiveId = this._activeEventId;
      }
    } catch (_) {
      this._activeEventId = null;
      this._activeEvent = null;
    }
  }

  _posterCell(player: RegPlayer) {
    const html = window.McPanel.html;
    const poster = this._postersByPlayer[String(player.id)] || null;
    if (!poster) {
      return html`<span class="poster-missing">—</span>`;
    }
    const href = poster.poster_url || "";
    const video = poster.video_url || "";
    if (video) {
      return html`<a href=${href} target="_blank" rel="noopener" title="Open poster">
        <video class="poster-thumb" src=${video} muted playsinline></video>
        open
      </a>`;
    }
    return html`<a href=${href} target="_blank" rel="noopener">open</a>`;
  }

  _openFactionMenu(catId: string) {
    if (this._factionBlurTimer) {
      clearTimeout(this._factionBlurTimer);
      this._factionBlurTimer = null;
    }
    this._factionOpenId = catId;
  }

  _scheduleCloseFactionMenu(catId: string) {
    if (this._factionBlurTimer) clearTimeout(this._factionBlurTimer);
    this._factionBlurTimer = setTimeout(() => {
      if (this._factionOpenId === catId) this._factionOpenId = "";
      this._factionBlurTimer = null;
    }, 150);
  }

  /** Dropdown (or Faction combobox) for one category — one selection each. */
  _affField(
    cat: AffCategory,
    value: string,
    onChange: (v: string) => void
  ) {
    const html = window.McPanel.html;
    const choices = cat.affiliations || [];
    const label = cat.name || "Affiliation";
    if (isFactionCategory(cat.name)) {
      const open = this._factionOpenId === cat.id;
      const filtered = filterChoices(choices, value);
      const exact = findChoiceExact(choices, value);
      const typed = (value || "").trim();
      const showCreateHint = Boolean(typed) && !exact;
      return html`
        <label for=${`aff-${cat.id}`}>${label}</label>
        <div class="aff-group aff-combo">
          <input
            id=${`aff-${cat.id}`}
            type="text"
            autocomplete="off"
            role="combobox"
            aria-expanded=${open ? "true" : "false"}
            aria-autocomplete="list"
            placeholder=${choices.length
              ? "Click to pick or type a new faction…"
              : "Type a new faction…"}
            .value=${value}
            @focus=${() => this._openFactionMenu(cat.id)}
            @click=${() => this._openFactionMenu(cat.id)}
            @input=${(e: Event) => {
              onChange((e.target as HTMLInputElement).value);
              this._openFactionMenu(cat.id);
            }}
            @keydown=${(e: KeyboardEvent) => {
              if (e.key === "Escape") this._factionOpenId = "";
              if (e.key === "ArrowDown") this._openFactionMenu(cat.id);
            }}
            @blur=${() => this._scheduleCloseFactionMenu(cat.id)}
          />
          ${open
            ? html`<ul class="aff-combo-menu" role="listbox">
                ${filtered.length === 0 && !showCreateHint
                  ? html`<li class="create-hint">
                      ${choices.length
                        ? "No matching factions"
                        : "No factions yet — type a name to create one"}
                    </li>`
                  : filtered.map(
                      (c) => html`<li
                        role="option"
                        class=${exact?.id === c.id ? "active" : ""}
                        @mousedown=${(e: Event) => {
                          e.preventDefault();
                          onChange(c.name || "");
                          this._factionOpenId = "";
                        }}
                      >
                        ${c.name}
                      </li>`
                    )}
                ${showCreateHint
                  ? html`<li class="create-hint">
                      Press Create/Save to add “${typed}” as a new faction
                    </li>`
                  : ""}
              </ul>`
            : ""}
          <p class="aff-hint">
            Click the field to open the list, or type a new faction name.
          </p>
        </div>
      `;
    }
    const active = findChoiceExact(choices, value)?.name || "";
    return html`
      <label for=${`aff-${cat.id}`}>${label}</label>
      <div class="aff-group">
        ${choices.length === 0
          ? html`<p class="aff-hint">
              No choices yet — add them in Game Master.
            </p>`
          : html`<select
              id=${`aff-${cat.id}`}
              .value=${active}
              @change=${(e: Event) => {
                onChange((e.target as HTMLSelectElement).value);
              }}
            >
              <option value="">Select…</option>
              ${choices.map(
                (c) => html`<option
                  value=${c.name || ""}
                  ?selected=${active === c.name}
                >
                  ${c.name}
                </option>`
              )}
            </select>`}
      </div>
    `;
  }

  _affiliationChips(affiliations: PlayerAffiliation[] | undefined) {
    const html = window.McPanel.html;
    const rows = (affiliations || []).filter((a) =>
      (a.affiliation_name || "").trim()
    );
    if (!rows.length) return html`<span class="poster-missing">—</span>`;
    return html`${rows.map(
      (a) => html`<span class="chip-static"
        ><span class="chip-cat">${(a.category_name || "Category").trim()}</span
        >${(a.affiliation_name || "").trim()}</span
      >`
    )}`;
  }

  async _syncNow() {
    try {
      await this.hass!.callService("registration", "sync_now", {});
      this._feedback("Syncing…", "ok");
      setTimeout(async () => {
        await this._loadAll();
      }, 800);
    } catch (err) {
      this._feedback("Sync failed: " + this._formatErr(err), "err");
    }
  }

  async _createEvent() {
    const name = this._evCreateName.trim();
    const venue = this._evCreateVenue.trim();
    const setActive = this._evCreateSetActive;
    if (!name) {
      this._feedback("Enter an event name", "warn");
      return;
    }
    try {
      await this.hass!.callService("registration", "create_event", {
        name,
        venue_name: venue,
        set_active: setActive,
      });
      // Optimistic label — don't flash UUID while WS reloads
      if (setActive) {
        this._activeEvent = {
          name,
          venue_name: venue || null,
          id: this._activeEventId || undefined,
        };
      }
      this._feedback(
        setActive
          ? `Created and activated “${name}”`
          : `Created event “${name}”`,
        "ok"
      );
      this._evCreateName = "";
      this._evCreateVenue = "";
      await this._loadEvents();
      await this._loadActiveEvent();
      // Prefer the name we just created if MCS memory only has the id
      if (setActive && !(this._activeEvent?.name || "").trim()) {
        this._activeEvent = {
          ...(this._activeEvent || {}),
          id: this._activeEventId || this._activeEvent?.id,
          name,
          venue_name: venue || null,
        };
      }
      if (setActive) {
        await this.hass!.callService("registration", "sync_now", {});
        await this._loadRoster();
      }
    } catch (err) {
      this._feedback("Create event failed: " + this._formatErr(err), "err");
    }
  }

  _onEditEventPick(eventId: string) {
    this._evEditId = eventId;
    const ev = this._events.find((e) => String(e.id) === String(eventId));
    this._evEditName = ev?.name || "";
    this._evEditVenue = ev?.venue_name || "";
  }

  async _updateEvent() {
    if (!this._evEditId) {
      this._feedback("Pick an event to edit", "warn");
      return;
    }
    const payload: {
      event_id: string;
      name?: string;
      venue_name?: string;
    } = { event_id: this._evEditId };
    if (this._evEditName.trim()) payload.name = this._evEditName.trim();
    payload.venue_name = this._evEditVenue.trim() || "";
    try {
      await this.hass!.callService("registration", "update_event", payload);
      this._feedback("Event updated", "ok");
      await this._loadEvents();
      await this._loadActiveEvent();
    } catch (err) {
      this._feedback("Update event failed: " + this._formatErr(err), "err");
    }
  }

  async _setActiveEvent() {
    if (!this._evSetActiveId) {
      this._feedback("Pick an event to activate", "warn");
      return;
    }
    try {
      await this.hass!.callService("registration", "set_active_event", {
        event_id: this._evSetActiveId,
      });
      this._feedback("Active event saved", "ok");
      await this._loadActiveEvent();
      await this.hass!.callService("registration", "sync_now", {});
      await this._loadRoster();
      await this._loadEvents();
      await this._loadTeams();
      await this._loadCatalog();
    } catch (err) {
      this._feedback("Set active failed: " + this._formatErr(err), "err");
    }
  }

  _beginEdit(p: RegPlayer) {
    this._editId = String(p.id ?? "");
    this._fName = (p.name || "").slice(0, PLAYER_NAME_MAX);
    this._fEmail = p.email || "";
    this._editTeamId = p.team_id ? String(p.team_id) : "";
    this._editActive = p.active !== false;
    this._nameStatus = "";
    const map: Record<string, string> = {};
    const prev: Record<string, string> = {};
    for (const cat of this._catalog.categories || []) {
      const assigned = playerAssignmentForCategory(p.affiliations, cat);
      map[cat.id] = assigned;
      const match = findChoiceExact(cat.affiliations || [], assigned);
      if (match) prev[cat.id] = match.id;
    }
    this._fAffByCat = map;
    this._editPrevAff = prev;
    this._checkName(this._fName);
  }

  _cancelEdit() {
    this._clearForm();
  }

  async _saveEdit() {
    if (!this._editId) return;
    const name = this._fName.trim();
    if (!name) {
      this._feedback("Enter a name", "warn");
      return;
    }
    if (name.length > PLAYER_NAME_MAX) {
      this._feedback(`Name must be at most ${PLAYER_NAME_MAX} characters`, "warn");
      return;
    }
    this._checkName(name);
    if (this._nameStatus === "taken") {
      this._feedback("Pick an unused name", "warn");
      return;
    }
    const payload: Record<string, unknown> = {
      player_id: this._editId,
      name,
      active: this._editActive,
    };
    const email = this._fEmail.trim();
    if (email) payload.email = email;
    else payload.clear_email = true;
    if (this._editTeamId) payload.team_id = this._editTeamId;
    else payload.clear_team = true;
    try {
      const affiliations = await this._resolveAffiliationsPayload(
        { ...this._fAffByCat },
        this._editPrevAff
      );
      if (Object.keys(affiliations).length) {
        payload.affiliations = affiliations;
      }
      await this.hass!.callService("registration", "update_player", payload);
      this._feedback(`Updated ${name}`, "ok");
      this._clearForm();
      await this.hass!.callService("registration", "sync_now", {});
      await this._loadRoster();
      await this._loadCatalog();
      if (!this._editId) this._applyCreateDefaults();
    } catch (err) {
      this._feedback("Update failed: " + this._formatErr(err), "err");
    }
  }

  async _deactivatePlayer(p: RegPlayer) {
    const id = String(p.id ?? "");
    if (!id) return;
    const label = p.name || id;
    if (!window.confirm(`Deactivate ${label}? They stay on the roster as inactive.`)) {
      return;
    }
    try {
      await this.hass!.callService("registration", "delete_player", {
        player_id: id,
      });
      this._feedback(`Deactivated ${label}`, "ok");
      if (this._editId === id) this._cancelEdit();
      await this.hass!.callService("registration", "sync_now", {});
      await this._loadRoster();
    } catch (err) {
      this._feedback("Deactivate failed: " + this._formatErr(err), "err");
    }
  }

  async _savePlayer() {
    const payload = this._formPayload();
    if (!payload.name) {
      this._feedback("Enter a name", "warn");
      return;
    }
    if (payload.name.length > PLAYER_NAME_MAX) {
      this._feedback(`Name must be at most ${PLAYER_NAME_MAX} characters`, "warn");
      return;
    }
    this._checkName(payload.name);
    if (this._nameStatus === "taken") {
      this._feedback("Pick an unused name", "warn");
      return;
    }
    if (!this._activeEventId) {
      this._feedback(
        "No active event — create or set one in the Events strip first",
        "err"
      );
      return;
    }
    try {
      const affiliations = await this._resolveAffiliationsPayload({
        ...this._fAffByCat,
      });
      if (Object.keys(affiliations).length) {
        payload.affiliations = affiliations;
      }
      await this.hass!.callService("registration", "register_player", payload);
      this._highlightName = payload.name;
      this._feedback(`Registered ${payload.name}`, "ok");
      this._clearForm();
      await this.hass!.callService("registration", "sync_now", {});
      await this._loadRoster();
      await this._loadCatalog();
      if (!this._editId) this._applyCreateDefaults();
      const match = this._roster.find(
        (p) =>
          (p.name || "").trim().toLowerCase() ===
          this._highlightName.trim().toLowerCase()
      );
      if (match?.pdn_code) {
        this._feedback(
          `Registered ${match.name} — PDN ${match.pdn_code}`,
          "ok"
        );
      }
    } catch (err) {
      const msg = this._formatErr(err);
      this._feedback("Register failed: " + msg, "err");
    }
  }

  override render() {
    const html = window.McPanel.html;
    const count = this._roster.length;
    const filtered = this._filteredRoster();
    const loadFailed =
      !this.hass ||
      (this._feedbackKind === "err" &&
        String(this._feedbackMsg).includes("Could not load roster"));
    const eventOptions =
      this._events.length > 0
        ? this._events
        : [];

    return html`
      <div class="wrap">
        <header class="page-header">
          <div class="header-row">
            <div>
              <h1>Registration</h1>
              <p class="sub">
                Events and player roster via Mission Control
                ${count
                  ? html` · ${count} player${count === 1 ? "" : "s"}`
                  : ""}
              </p>
            </div>
            <button class="btn-ghost" @click=${() => this._syncNow()}>
              Sync Now
            </button>
          </div>
        </header>

        <div class="layout">
          <div class="form-col">
            <div class="events-block">
              <h2 class="form-title">Events</h2>
              <p class="active-line">
                Active:
                <strong>${this._activeLabel()}</strong>
              </p>
              ${!this._eventsReady && this._eventsDetail
                ? html`<p class="events-gate">${this._eventsDetail}</p>`
                : ""}
              <div class="mode-toggle" role="tablist" aria-label="Event action">
                <button
                  type="button"
                  class=${this._evMode === "create" ? "active" : ""}
                  @click=${() => {
                    this._evMode = "create";
                  }}
                >
                  Create
                </button>
                <button
                  type="button"
                  class=${this._evMode === "edit" ? "active" : ""}
                  @click=${() => {
                    this._evMode = "edit";
                  }}
                >
                  Edit
                </button>
                <button
                  type="button"
                  class=${this._evMode === "set" ? "active" : ""}
                  @click=${() => {
                    this._evMode = "set";
                  }}
                >
                  Set
                </button>
              </div>

              ${this._evMode === "create"
                ? html`
                    <label for="ev-create-name">Name</label>
                    <input
                      id="ev-create-name"
                      type="text"
                      .value=${this._evCreateName}
                      @input=${(e: Event) => {
                        this._evCreateName = (
                          e.target as HTMLInputElement
                        ).value;
                      }}
                    />
                    <label for="ev-create-venue">Venue (optional)</label>
                    <input
                      id="ev-create-venue"
                      type="text"
                      .value=${this._evCreateVenue}
                      @input=${(e: Event) => {
                        this._evCreateVenue = (
                          e.target as HTMLInputElement
                        ).value;
                      }}
                    />
                    <label class="check-row">
                      <input
                        type="checkbox"
                        .checked=${this._evCreateSetActive}
                        @change=${(e: Event) => {
                          this._evCreateSetActive = (
                            e.target as HTMLInputElement
                          ).checked;
                        }}
                      />
                      Set active after create
                    </label>
                    <button
                      class="btn-create"
                      @click=${() => this._createEvent()}
                    >
                      Create event
                    </button>
                  `
                : this._evMode === "edit"
                  ? html`
                      <label for="ev-edit-pick">Event</label>
                      <select
                        id="ev-edit-pick"
                        .value=${this._evEditId}
                        ?disabled=${eventOptions.length === 0}
                        @change=${(e: Event) => {
                          this._onEditEventPick(
                            (e.target as HTMLSelectElement).value
                          );
                        }}
                      >
                        <option value="">
                          ${eventOptions.length
                            ? "Select…"
                            : "No cached events yet — create one"}
                        </option>
                        ${eventOptions.map(
                          (ev) =>
                            html`<option value=${ev.id ?? ""}>
                              ${ev.name || ev.id}
                            </option>`
                        )}
                      </select>
                      <label for="ev-edit-name">Name</label>
                      <input
                        id="ev-edit-name"
                        type="text"
                        .value=${this._evEditName}
                        @input=${(e: Event) => {
                          this._evEditName = (
                            e.target as HTMLInputElement
                          ).value;
                        }}
                      />
                      <label for="ev-edit-venue">Venue</label>
                      <input
                        id="ev-edit-venue"
                        type="text"
                        .value=${this._evEditVenue}
                        @input=${(e: Event) => {
                          this._evEditVenue = (
                            e.target as HTMLInputElement
                          ).value;
                        }}
                      />
                      <button
                        class="btn-ghost"
                        ?disabled=${!this._evEditId}
                        @click=${() => this._updateEvent()}
                      >
                        Save event
                      </button>
                    `
                  : html`
                      <label for="ev-set-active">Event</label>
                      <select
                        id="ev-set-active"
                        .value=${this._evSetActiveId}
                        ?disabled=${eventOptions.length === 0}
                        @change=${(e: Event) => {
                          this._evSetActiveId = (
                            e.target as HTMLSelectElement
                          ).value;
                        }}
                      >
                        <option value="">
                          ${eventOptions.length
                            ? "Select…"
                            : "No cached events yet — create one"}
                        </option>
                        ${eventOptions.map(
                          (ev) =>
                            html`<option value=${ev.id ?? ""}>
                              ${ev.name || ev.id}
                            </option>`
                        )}
                      </select>
                      <button
                        class="btn-create"
                        ?disabled=${!this._evSetActiveId}
                        @click=${() => this._setActiveEvent()}
                      >
                        Set active
                      </button>
                    `}
            </div>

            <h2 class="form-title">
              ${this._editId ? "Edit player" : "Register player"}
            </h2>
            <label for="f-name">Name</label>
            <input
              id="f-name"
              type="text"
              maxlength=${PLAYER_NAME_MAX}
              autocomplete="off"
              .value=${this._fName}
              @input=${(e: Event) => {
                this._onNameInput((e.target as HTMLInputElement).value);
              }}
            />
            <p class="name-hint">
              Max ${PLAYER_NAME_MAX} characters (${this._fName.length}/${PLAYER_NAME_MAX})
            </p>
            <div
              id="name-status"
              class="name-status ${this._nameStatus === "available"
                ? "status-ok"
                : this._nameStatus === "taken"
                  ? "status-err"
                  : ""}"
            >
              ${this._nameStatus === "available"
                ? "Name is available"
                : this._nameStatus === "taken"
                  ? "Name is already in use"
                  : ""}
            </div>
            <label for="f-email">Email (optional)</label>
            <input
              id="f-email"
              type="email"
              autocomplete="off"
              .value=${this._fEmail}
              @input=${(e: Event) => {
                this._fEmail = (e.target as HTMLInputElement).value;
              }}
            />
            ${this._editId
              ? html`
                  <label for="f-team">Team</label>
                  <select
                    id="f-team"
                    .value=${this._editTeamId}
                    @change=${(e: Event) => {
                      this._editTeamId = (e.target as HTMLSelectElement).value;
                    }}
                  >
                    <option value="">Unassigned</option>
                    ${this._teams.map(
                      (t) =>
                        html`<option
                          value=${t.id ?? ""}
                          ?selected=${this._editTeamId === String(t.id ?? "")}
                        >
                          ${t.name || t.id}
                        </option>`
                    )}
                  </select>
                `
              : ""}
            ${(this._catalog.categories || []).map((cat) =>
              this._affField(cat, this._fAffByCat[cat.id] || "", (v) => {
                this._fAffByCat = { ...this._fAffByCat, [cat.id]: v };
              })
            )}
            ${(this._catalog.categories || []).length === 0
              ? html`<p class="aff-hint">
                  No affiliation categories yet — add them in Game Master.
                </p>`
              : ""}
            ${this._editId
              ? html`<label class="check-row">
                  <input
                    type="checkbox"
                    .checked=${this._editActive}
                    @change=${(e: Event) => {
                      this._editActive = (e.target as HTMLInputElement).checked;
                    }}
                  />
                  Active registration
                </label>`
              : ""}
            <div class="form-actions">
              ${this._editId
                ? html`
                    <button class="btn-create" @click=${() => this._saveEdit()}>
                      Save player
                    </button>
                    <button class="btn-ghost" @click=${() => this._cancelEdit()}>
                      Cancel
                    </button>
                  `
                : html`
                    <button class="btn-create" @click=${() => this._savePlayer()}>
                      Create player
                    </button>
                    <button class="btn-ghost" @click=${() => this._syncNow()}>
                      Refresh table
                    </button>
                  `}
            </div>

            ${this._feedbackTemplate()}
          </div>

          <div class="table-col">
            <h2 class="form-title">Player Database</h2>
            <div class="search-row">
              <input
                id="search"
                type="search"
                placeholder="Search by name, PDN, email…"
                .value=${this._search}
                @input=${(e: Event) => {
                  this._search = (e.target as HTMLInputElement).value;
                }}
              />
            </div>
            ${loadFailed && count === 0
              ? html`<p class="empty" style="color:var(--error-color,#f44336)">
                  Could not load roster.
                </p>`
              : filtered.length === 0
                ? html`<p class="empty">
                    ${count === 0
                      ? "No players yet"
                      : "No players match search"}
                  </p>`
                : html`
                    <table class="roster-table">
                      <thead>
                        <tr>
                          <th>PDN</th>
                          <th>Name</th>
                          <th>Team</th>
                          <th>Affiliations</th>
                          <th>Status</th>
                          <th>Created</th>
                          <th>Email</th>
                          <th>Poster</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        ${filtered.map((p) => {
                          const highlighted =
                            this._highlightName &&
                            (p.name || "").trim().toLowerCase() ===
                              this._highlightName.trim().toLowerCase();
                          return html`
                            <tr class=${highlighted ? "highlight" : ""}>
                              <td>${p.pdn_code ?? ""}</td>
                              <td>${p.name ?? ""}</td>
                              <td>${this._teamOf(p)}</td>
                              <td>${this._affiliationChips(p.affiliations)}</td>
                              <td>${this._activeOf(p)}</td>
                              <td>${this._formatCreated(p.created_at)}</td>
                              <td>${p.email ?? ""}</td>
                              <td class="poster-cell">${this._posterCell(p)}</td>
                              <td class="actions-cell">
                                <button
                                  class="edit-btn"
                                  @click=${() => this._beginEdit(p)}
                                >
                                  Edit
                                </button>
                                <button
                                  class="delete-btn"
                                  title="Soft-deactivate (keeps roster row)"
                                  ?disabled=${p.active === false}
                                  @click=${() => this._deactivatePlayer(p)}
                                >
                                  Deactivate
                                </button>
                              </td>
                            </tr>
                          `;
                        })}
                      </tbody>
                    </table>
                  `}
          </div>
        </div>
      </div>
    `;
  }
}

customElements.define("registration-panel", RegistrationPanel);
