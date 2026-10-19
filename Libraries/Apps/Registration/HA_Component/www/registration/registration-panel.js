"use strict";
(() => {
  // src/panels/registration-panel.ts
  var RegistrationPanel = class extends window.McPanel.Base {
    constructor() {
      super();
      this._checkTimer = null;
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
      this._editId = "";
      this._editName = "";
      this._editEmail = "";
      this._editTeamId = "";
      this._editActive = true;
    }
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
        _editId: { state: true },
        _editName: { state: true },
        _editEmail: { state: true },
        _editTeamId: { state: true },
        _editActive: { state: true }
      };
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
        @media (max-width: 900px) {
          .layout {
            grid-template-columns: 1fr;
          }
          .form-col {
            border-right: 0;
            border-bottom: 1px solid var(--divider-color, #1f3a44);
          }
        }
      `
      ];
    }
    disconnectedCallback() {
      if (this._checkTimer) {
        clearTimeout(this._checkTimer);
        this._checkTimer = null;
      }
      super.disconnectedCallback();
    }
    _token() {
      return this.hass?.auth?.data?.access_token || "";
    }
    _formatErr(err) {
      if (err == null) return "unknown error";
      if (typeof err === "string") return err;
      const e = err;
      if (typeof e.error === "object" && e.error?.message) return e.error.message;
      if (typeof e.error === "string") return e.error;
      return e.message || e.code || JSON.stringify(err);
    }
    _formPayload() {
      const payload = {
        name: this._fName.trim()
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
    _onNameInput(value) {
      this._fName = value;
      if (this._checkTimer) clearTimeout(this._checkTimer);
      this._checkTimer = setTimeout(() => this._checkName(value), 300);
    }
    _checkName(name) {
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
    _filteredRoster() {
      const term = this._search.trim().toLowerCase();
      if (!term) return this._roster;
      return this._roster.filter(
        (p) => String(p.id ?? "").toLowerCase().includes(term) || String(p.name ?? "").toLowerCase().includes(term) || String(p.pdn_code ?? "").toLowerCase().includes(term) || String(p.email ?? "").toLowerCase().includes(term)
      );
    }
    _teamOf(p) {
      const name = (p.team_name || "").trim();
      if (name) return name;
      if (p.team_id) return String(p.team_id);
      return "Unassigned";
    }
    _activeOf(p) {
      return p.active === false ? "Inactive" : "Active";
    }
    _formatCreated(value) {
      if (!value) return "";
      try {
        const d = new Date(value);
        if (Number.isNaN(d.getTime())) return value;
        return d.toLocaleString();
      } catch {
        return value;
      }
    }
    _activeLabel() {
      const fromActive = (this._activeEvent?.name || "").trim();
      if (fromActive) return fromActive;
      if (this._activeEventId) {
        const cached = this._events.find(
          (e) => String(e.id) === String(this._activeEventId)
        );
        const fromCache = (cached?.name || "").trim();
        if (fromCache) return fromCache;
        return this._activeEventId;
      }
      return "None \u2014 create or set an active event before registering players";
    }
    async _boot() {
      await this._loadAll();
    }
    async _loadAll() {
      await Promise.all([
        this._loadRoster(),
        this._loadEvents(),
        this._loadActiveEvent(),
        this._loadPosters()
      ]);
      await this._loadTeams();
    }
    async _loadTeams() {
      try {
        const result = await this.hass.callWS({
          type: "registration/get_teams",
          event_id: this._activeEventId || void 0
        });
        this._teams = result?.teams ?? [];
      } catch (_) {
        this._teams = [];
      }
    }
    async _loadPosters() {
      this._postersByPlayer = {};
      try {
        const headers = { "cache-control": "no-store" };
        if (this._token()) headers.Authorization = `Bearer ${this._token()}`;
        const q = this._activeEventId ? `?event_id=${encodeURIComponent(this._activeEventId)}` : "";
        const resp = await fetch(`/api/gbn/proxy/api/posters${q}`, {
          headers,
          credentials: "same-origin",
          cache: "no-store"
        });
        if (!resp.ok) return;
        const list = await resp.json();
        if (!Array.isArray(list)) return;
        const map = {};
        for (const p of list) {
          const id = String(p.player_id || "");
          if (id) map[id] = p;
        }
        this._postersByPlayer = map;
      } catch (_) {
      }
    }
    async _loadRoster() {
      try {
        const result = await this.hass.callWS({
          type: "registration/get_roster"
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
        const result = await this.hass.callWS({ type: "registration/get_events" });
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
        const result = await this.hass.callWS({ type: "registration/get_active_event" });
        this._activeEventId = result?.active_event_id ?? null;
        let event = result?.event ?? null;
        if (event && !(event.name || "").trim() && this._activeEventId) {
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
    _posterCell(player) {
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
        await this.hass.callService("registration", "sync_now", {});
        this._feedback("Syncing\u2026", "ok");
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
        await this.hass.callService("registration", "create_event", {
          name,
          venue_name: venue,
          set_active: setActive
        });
        if (setActive) {
          this._activeEvent = {
            name,
            venue_name: venue || null,
            id: this._activeEventId || void 0
          };
        }
        this._feedback(
          setActive ? `Created and activated \u201C${name}\u201D` : `Created event \u201C${name}\u201D`,
          "ok"
        );
        this._evCreateName = "";
        this._evCreateVenue = "";
        await this._loadEvents();
        await this._loadActiveEvent();
        if (setActive && !(this._activeEvent?.name || "").trim()) {
          this._activeEvent = {
            ...this._activeEvent || {},
            id: this._activeEventId || this._activeEvent?.id,
            name,
            venue_name: venue || null
          };
        }
        if (setActive) {
          await this.hass.callService("registration", "sync_now", {});
          await this._loadRoster();
        }
      } catch (err) {
        this._feedback("Create event failed: " + this._formatErr(err), "err");
      }
    }
    _onEditEventPick(eventId) {
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
      const payload = { event_id: this._evEditId };
      if (this._evEditName.trim()) payload.name = this._evEditName.trim();
      payload.venue_name = this._evEditVenue.trim() || "";
      try {
        await this.hass.callService("registration", "update_event", payload);
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
        await this.hass.callService("registration", "set_active_event", {
          event_id: this._evSetActiveId
        });
        this._feedback("Active event saved", "ok");
        await this._loadActiveEvent();
        await this.hass.callService("registration", "sync_now", {});
        await this._loadRoster();
        await this._loadEvents();
        await this._loadTeams();
      } catch (err) {
        this._feedback("Set active failed: " + this._formatErr(err), "err");
      }
    }
    _beginEdit(p) {
      this._editId = String(p.id ?? "");
      this._editName = p.name || "";
      this._editEmail = p.email || "";
      this._editTeamId = p.team_id ? String(p.team_id) : "";
      this._editActive = p.active !== false;
    }
    _cancelEdit() {
      this._editId = "";
      this._editName = "";
      this._editEmail = "";
      this._editTeamId = "";
      this._editActive = true;
    }
    async _saveEdit() {
      if (!this._editId) return;
      const name = this._editName.trim();
      if (!name) {
        this._feedback("Enter a name", "warn");
        return;
      }
      const payload = {
        player_id: this._editId,
        name,
        active: this._editActive
      };
      const email = this._editEmail.trim();
      if (email) payload.email = email;
      else payload.clear_email = true;
      if (this._editTeamId) payload.team_id = this._editTeamId;
      else payload.clear_team = true;
      try {
        await this.hass.callService("registration", "update_player", payload);
        this._feedback(`Updated ${name}`, "ok");
        this._cancelEdit();
        await this.hass.callService("registration", "sync_now", {});
        await this._loadRoster();
      } catch (err) {
        this._feedback("Update failed: " + this._formatErr(err), "err");
      }
    }
    async _deactivatePlayer(p) {
      const id = String(p.id ?? "");
      if (!id) return;
      const label = p.name || id;
      if (!window.confirm(`Deactivate ${label}? They stay on the roster as inactive.`)) {
        return;
      }
      try {
        await this.hass.callService("registration", "delete_player", {
          player_id: id
        });
        this._feedback(`Deactivated ${label}`, "ok");
        if (this._editId === id) this._cancelEdit();
        await this.hass.callService("registration", "sync_now", {});
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
      this._checkName(payload.name);
      if (this._nameStatus === "taken") {
        this._feedback("Pick an unused name", "warn");
        return;
      }
      if (!this._activeEventId) {
        this._feedback(
          "No active event \u2014 create or set one in the Events strip first",
          "err"
        );
        return;
      }
      try {
        await this.hass.callService("registration", "register_player", payload);
        this._highlightName = payload.name;
        this._feedback(`Registered ${payload.name}`, "ok");
        this._clearForm();
        await this.hass.callService("registration", "sync_now", {});
        await this._loadRoster();
        const match = this._roster.find(
          (p) => (p.name || "").trim().toLowerCase() === this._highlightName.trim().toLowerCase()
        );
        if (match?.pdn_code) {
          this._feedback(
            `Registered ${match.name} \u2014 PDN ${match.pdn_code}`,
            "ok"
          );
        }
      } catch (err) {
        const msg = this._formatErr(err);
        this._feedback("Register failed: " + msg, "err");
      }
    }
    render() {
      const html = window.McPanel.html;
      const count = this._roster.length;
      const filtered = this._filteredRoster();
      const loadFailed = !this.hass || this._feedbackKind === "err" && String(this._feedbackMsg).includes("Could not load roster");
      const eventOptions = this._events.length > 0 ? this._events : [];
      return html`
      <div class="wrap">
        <header class="page-header">
          <div class="header-row">
            <div>
              <h1>Registration</h1>
              <p class="sub">
                Events and player roster via Mission Control
                ${count ? html` · ${count} player${count === 1 ? "" : "s"}` : ""}
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
              ${!this._eventsReady && this._eventsDetail ? html`<p class="events-gate">${this._eventsDetail}</p>` : ""}
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

              ${this._evMode === "create" ? html`
                    <label for="ev-create-name">Name</label>
                    <input
                      id="ev-create-name"
                      type="text"
                      .value=${this._evCreateName}
                      @input=${(e) => {
        this._evCreateName = e.target.value;
      }}
                    />
                    <label for="ev-create-venue">Venue (optional)</label>
                    <input
                      id="ev-create-venue"
                      type="text"
                      .value=${this._evCreateVenue}
                      @input=${(e) => {
        this._evCreateVenue = e.target.value;
      }}
                    />
                    <label class="check-row">
                      <input
                        type="checkbox"
                        .checked=${this._evCreateSetActive}
                        @change=${(e) => {
        this._evCreateSetActive = e.target.checked;
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
                  ` : this._evMode === "edit" ? html`
                      <label for="ev-edit-pick">Event</label>
                      <select
                        id="ev-edit-pick"
                        .value=${this._evEditId}
                        ?disabled=${eventOptions.length === 0}
                        @change=${(e) => {
        this._onEditEventPick(
          e.target.value
        );
      }}
                      >
                        <option value="">
                          ${eventOptions.length ? "Select\u2026" : "No cached events yet \u2014 create one"}
                        </option>
                        ${eventOptions.map(
        (ev) => html`<option value=${ev.id ?? ""}>
                              ${ev.name || ev.id}
                            </option>`
      )}
                      </select>
                      <label for="ev-edit-name">Name</label>
                      <input
                        id="ev-edit-name"
                        type="text"
                        .value=${this._evEditName}
                        @input=${(e) => {
        this._evEditName = e.target.value;
      }}
                      />
                      <label for="ev-edit-venue">Venue</label>
                      <input
                        id="ev-edit-venue"
                        type="text"
                        .value=${this._evEditVenue}
                        @input=${(e) => {
        this._evEditVenue = e.target.value;
      }}
                      />
                      <button
                        class="btn-ghost"
                        ?disabled=${!this._evEditId}
                        @click=${() => this._updateEvent()}
                      >
                        Save event
                      </button>
                    ` : html`
                      <label for="ev-set-active">Event</label>
                      <select
                        id="ev-set-active"
                        .value=${this._evSetActiveId}
                        ?disabled=${eventOptions.length === 0}
                        @change=${(e) => {
        this._evSetActiveId = e.target.value;
      }}
                      >
                        <option value="">
                          ${eventOptions.length ? "Select\u2026" : "No cached events yet \u2014 create one"}
                        </option>
                        ${eventOptions.map(
        (ev) => html`<option value=${ev.id ?? ""}>
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

            <h2 class="form-title">Register player</h2>
            <label for="f-name">Name</label>
            <input
              id="f-name"
              type="text"
              autocomplete="off"
              .value=${this._fName}
              @input=${(e) => {
        this._onNameInput(e.target.value);
      }}
            />
            <div
              id="name-status"
              class="name-status ${this._nameStatus === "available" ? "status-ok" : this._nameStatus === "taken" ? "status-err" : ""}"
            >
              ${this._nameStatus === "available" ? "Name is available" : this._nameStatus === "taken" ? "Name is already in use" : ""}
            </div>
            <label for="f-email">Email (optional)</label>
            <input
              id="f-email"
              type="email"
              autocomplete="off"
              .value=${this._fEmail}
              @input=${(e) => {
        this._fEmail = e.target.value;
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

            ${this._editId ? html`
                  <h2 class="form-title" style="margin-top:28px">Edit player</h2>
                  <label for="edit-name">Name</label>
                  <input
                    id="edit-name"
                    type="text"
                    .value=${this._editName}
                    @input=${(e) => {
        this._editName = e.target.value;
      }}
                  />
                  <label for="edit-email">Email</label>
                  <input
                    id="edit-email"
                    type="email"
                    .value=${this._editEmail}
                    @input=${(e) => {
        this._editEmail = e.target.value;
      }}
                  />
                  <label for="edit-team">Team</label>
                  <select
                    id="edit-team"
                    .value=${this._editTeamId}
                    @change=${(e) => {
        this._editTeamId = e.target.value;
      }}
                  >
                    <option value="">Unassigned</option>
                    ${this._teams.map(
        (t) => html`<option value=${t.id ?? ""}>
                          ${t.name || t.id}
                        </option>`
      )}
                  </select>
                  <label class="check-row">
                    <input
                      type="checkbox"
                      .checked=${this._editActive}
                      @change=${(e) => {
        this._editActive = e.target.checked;
      }}
                    />
                    Active registration
                  </label>
                  <div class="form-actions">
                    <button class="btn-create" @click=${() => this._saveEdit()}>
                      Save player
                    </button>
                    <button class="btn-ghost" @click=${() => this._cancelEdit()}>
                      Cancel
                    </button>
                  </div>
                ` : ""}
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
                @input=${(e) => {
        this._search = e.target.value;
      }}
              />
            </div>
            ${loadFailed && count === 0 ? html`<p class="empty" style="color:var(--error-color,#f44336)">
                  Could not load roster.
                </p>` : filtered.length === 0 ? html`<p class="empty">
                    ${count === 0 ? "No players yet" : "No players match search"}
                  </p>` : html`
                    <table class="roster-table">
                      <thead>
                        <tr>
                          <th>PDN</th>
                          <th>Name</th>
                          <th>Team</th>
                          <th>Status</th>
                          <th>Created</th>
                          <th>Email</th>
                          <th>Poster</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        ${filtered.map((p) => {
        const highlighted = this._highlightName && (p.name || "").trim().toLowerCase() === this._highlightName.trim().toLowerCase();
        return html`
                            <tr class=${highlighted ? "highlight" : ""}>
                              <td>${p.pdn_code ?? ""}</td>
                              <td>${p.name ?? ""}</td>
                              <td>${this._teamOf(p)}</td>
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
  };
  customElements.define("registration-panel", RegistrationPanel);
})();
//# sourceMappingURL=registration-panel.js.map
