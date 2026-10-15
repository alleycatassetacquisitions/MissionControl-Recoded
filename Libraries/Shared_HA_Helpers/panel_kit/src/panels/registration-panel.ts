/// <reference path="../mc-panel/globals.d.ts" />
/**
 * Registration panel — events strip + player roster via MCS.
 *
 * Design contract:
 *  - Extends McPanelBase from shared_libraries/mc-panel.js.
 *  - ALL data reads and writes go through hass.callWS / hass.callService.
 *    Zero direct fetch() calls to MCS or any LAN IP.
 *
 * Websocket:
 *  - registration/get_roster
 *  - registration/get_events (stub-aware)
 *  - registration/get_active_event
 *
 * HA services:
 *  - registration.sync_now
 *  - registration.register_player (name + email)
 *  - registration.create_event / update_event / set_active_event
 *  - update_player / delete_player kept but UI-disabled (Central pending)
 */

type RegPlayer = {
  id?: string | number;
  name?: string;
  pdn_code?: string;
  mode?: string;
  role?: string;
  created_at?: string;
  email?: string;
};

type RegEvent = {
  id?: string;
  name?: string;
  venue_name?: string | null;
  created_at?: string;
};

type RegPoster = {
  player_id?: string;
  poster_url?: string;
  video_url?: string;
};

const EDIT_DELETE_HINT = "Waiting on Central player update/delete";

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
      _evCreateName: { state: true },
      _evCreateVenue: { state: true },
      _evCreateSetActive: { state: true },
      _evEditId: { state: true },
      _evEditName: { state: true },
      _evEditVenue: { state: true },
      _evSetActiveId: { state: true },
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
  declare _evCreateName: string;
  declare _evCreateVenue: string;
  declare _evCreateSetActive: boolean;
  declare _evEditId: string;
  declare _evEditName: string;
  declare _evEditVenue: string;
  declare _evSetActiveId: string;

  private _checkTimer: ReturnType<typeof setTimeout> | null = null;

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
    this._evCreateName = "";
    this._evCreateVenue = "";
    this._evCreateSetActive = true;
    this._evEditId = "";
    this._evEditName = "";
    this._evEditVenue = "";
    this._evSetActiveId = "";
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
        .sub {
          color: var(--secondary-text-color, #7aa8b8);
          font-size: 13px;
          margin-top: 4px;
        }
        .events-strip {
          padding: 16px 24px;
          border-bottom: 1px solid var(--divider-color, #1f3a44);
          background: var(--secondary-background-color, #0d1418);
        }
        .events-strip h2 {
          margin: 0 0 8px;
          font-size: 14px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: var(--secondary-text-color, #7aa8b8);
        }
        .active-line {
          font-size: 14px;
          margin-bottom: 12px;
        }
        .active-line strong {
          color: var(--primary-color, #00e5ff);
        }
        .events-gate {
          font-size: 13px;
          color: var(--secondary-text-color, #7aa8b8);
          margin-bottom: 12px;
        }
        .events-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 16px;
        }
        .events-block {
          min-width: 0;
        }
        .events-block h3 {
          margin: 0 0 8px;
          font-size: 13px;
          font-weight: 600;
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
          background: var(--card-background-color, #10151c);
          color: var(--primary-text-color, #e8f6ff);
          border: 1px solid var(--divider-color, #1f3a44);
          border-radius: 6px;
          font: inherit;
        }
        .check-row {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 10px;
          font-size: 13px;
        }
        .check-row input {
          width: auto;
        }
        .events-block .btn-create,
        .events-block .btn-ghost {
          margin-top: 12px;
        }
        .layout {
          display: grid;
          grid-template-columns: 340px 1fr;
          min-height: calc(100vh - 220px);
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
        .form-col input {
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
        @media (max-width: 1100px) {
          .events-grid {
            grid-template-columns: 1fr;
          }
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

  _formPayload() {
    const payload: { name: string; email?: string } = {
      name: this._fName.trim(),
    };
    const email = this._fEmail.trim();
    if (email) payload.email = email;
    return payload;
  }

  _clearForm() {
    this._fName = "";
    this._fEmail = "";
    this._nameStatus = "";
    if (this._checkTimer) {
      clearTimeout(this._checkTimer);
      this._checkTimer = null;
    }
  }

  _onNameInput(value: string) {
    this._fName = value;
    if (this._checkTimer) clearTimeout(this._checkTimer);
    this._checkTimer = setTimeout(() => this._checkName(value), 300);
  }

  _checkName(name: string) {
    const trimmed = name.trim();
    if (!trimmed) {
      this._nameStatus = "";
      return;
    }
    const needle = trimmed.toLowerCase();
    const clash = this._roster.find(
      (p) => (p.name || "").trim().toLowerCase() === needle
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

  _modeOf(p: RegPlayer): string {
    return (p.mode || p.role || "unassigned").toString();
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
  }

  async _loadPosters() {
    this._postersByPlayer = {};
    try {
      const headers: Record<string, string> = { "cache-control": "no-store" };
      if (this._token()) headers.Authorization = `Bearer ${this._token()}`;
      const resp = await fetch("/api/gbn/proxy/api/posters", {
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
    } catch (err) {
      this._feedback("Set active failed: " + this._formatErr(err), "err");
    }
  }

  async _savePlayer() {
    const payload = this._formPayload();
    if (!payload.name) {
      this._feedback("Enter a name", "warn");
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
      await this.hass!.callService("registration", "register_player", payload);
      this._highlightName = payload.name;
      this._feedback(`Registered ${payload.name}`, "ok");
      this._clearForm();
      await this.hass!.callService("registration", "sync_now", {});
      await this._loadRoster();
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

        <section class="events-strip">
          <h2>Events</h2>
          <p class="active-line">
            Active:
            <strong>${this._activeLabel()}</strong>
          </p>
          ${!this._eventsReady
            ? html`<p class="events-gate">
                ${this._eventsDetail ||
                "Waiting on Central event list — create events below; the dropdown uses this session’s cache until list/active ships."}
              </p>`
            : ""}
          <div class="events-grid">
            <div class="events-block">
              <h3>Create event</h3>
              <label for="ev-create-name">Name</label>
              <input
                id="ev-create-name"
                type="text"
                .value=${this._evCreateName}
                @input=${(e: Event) => {
                  this._evCreateName = (e.target as HTMLInputElement).value;
                }}
              />
              <label for="ev-create-venue">Venue (optional)</label>
              <input
                id="ev-create-venue"
                type="text"
                .value=${this._evCreateVenue}
                @input=${(e: Event) => {
                  this._evCreateVenue = (e.target as HTMLInputElement).value;
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
              <button class="btn-create" @click=${() => this._createEvent()}>
                Create event
              </button>
            </div>

            <div class="events-block">
              <h3>Edit event</h3>
              <label for="ev-edit-pick">Event</label>
              <select
                id="ev-edit-pick"
                .value=${this._evEditId}
                ?disabled=${eventOptions.length === 0}
                @change=${(e: Event) => {
                  this._onEditEventPick((e.target as HTMLSelectElement).value);
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
                  this._evEditName = (e.target as HTMLInputElement).value;
                }}
              />
              <label for="ev-edit-venue">Venue</label>
              <input
                id="ev-edit-venue"
                type="text"
                .value=${this._evEditVenue}
                @input=${(e: Event) => {
                  this._evEditVenue = (e.target as HTMLInputElement).value;
                }}
              />
              <button
                class="btn-ghost"
                ?disabled=${!this._evEditId}
                @click=${() => this._updateEvent()}
              >
                Save event
              </button>
            </div>

            <div class="events-block">
              <h3>Set active</h3>
              <label for="ev-set-active">Event</label>
              <select
                id="ev-set-active"
                .value=${this._evSetActiveId}
                ?disabled=${eventOptions.length === 0}
                @change=${(e: Event) => {
                  this._evSetActiveId = (e.target as HTMLSelectElement).value;
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
            </div>
          </div>
        </section>

        <div class="layout">
          <div class="form-col">
            <h2 class="form-title">Register player</h2>
            <label for="f-name">Name</label>
            <input
              id="f-name"
              type="text"
              autocomplete="off"
              .value=${this._fName}
              @input=${(e: Event) => {
                this._onNameInput((e.target as HTMLInputElement).value);
              }}
            />
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
            <div class="form-actions">
              <button class="btn-create" @click=${() => this._savePlayer()}>
                Create player
              </button>
              <button class="btn-ghost" @click=${() => this._syncNow()}>
                Refresh table
              </button>
            </div>
            ${this._feedbackTemplate()}
          </div>

          <div class="table-col">
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
                          <th>Mode</th>
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
                              <td>${this._modeOf(p)}</td>
                              <td>${this._formatCreated(p.created_at)}</td>
                              <td>${p.email ?? ""}</td>
                              <td class="poster-cell">${this._posterCell(p)}</td>
                              <td class="actions-cell">
                                <button
                                  class="edit-btn"
                                  disabled
                                  title=${EDIT_DELETE_HINT}
                                >
                                  Edit
                                </button>
                                <button
                                  class="delete-btn"
                                  disabled
                                  title=${EDIT_DELETE_HINT}
                                >
                                  Delete
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
