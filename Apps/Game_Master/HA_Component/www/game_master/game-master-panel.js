"use strict";
(() => {
  // src/shared/affiliations.ts
  function emptyCatalog() {
    return { event_id: null, categories: [] };
  }

  // src/panels/game-master-panel.ts
  var GameMasterPanel = class extends window.McPanel.Base {
    static get properties() {
      return {
        ...super.properties,
        _state: { state: true },
        _busy: { state: true },
        // Events strip
        _events: { state: true },
        _eventsReady: { state: true },
        _eventsDetail: { state: true },
        _evMode: { state: true },
        _evCreateName: { state: true },
        _evCreateVenue: { state: true },
        _evCreateSetActive: { state: true },
        _evEditId: { state: true },
        _evEditName: { state: true },
        _evEditVenue: { state: true },
        _evSetActiveId: { state: true },
        // Affiliation catalog
        _catalog: { state: true },
        _catCreateName: { state: true },
        _choiceDrafts: { state: true },
        _renameCatId: { state: true },
        _renameCatName: { state: true },
        _renameChoiceKey: { state: true },
        _renameChoiceName: { state: true }
      };
    }
    constructor() {
      super();
      this._state = null;
      this._busy = false;
      this._events = [];
      this._eventsReady = false;
      this._eventsDetail = "";
      this._evMode = "create";
      this._evCreateName = "";
      this._evCreateVenue = "";
      this._evCreateSetActive = true;
      this._evEditId = "";
      this._evEditName = "";
      this._evEditVenue = "";
      this._evSetActiveId = "";
      this._catalog = emptyCatalog();
      this._catCreateName = "";
      this._choiceDrafts = {};
      this._renameCatId = "";
      this._renameCatName = "";
      this._renameChoiceKey = "";
      this._renameChoiceName = "";
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
          max-width: 720px;
          margin: 0 auto;
          padding: 0 20px 40px;
        }
        .page-header {
          padding: 28px 0 18px;
          border-bottom: 1px solid var(--divider-color, #1f3a44);
          margin-bottom: 28px;
        }
        .page-header h1 {
          margin: 0;
          font-size: 28px;
          letter-spacing: 0.02em;
        }
        .sub {
          color: var(--secondary-text-color, #7aa8b8);
          font-size: 14px;
          margin-top: 8px;
          line-height: 1.4;
        }
        .section {
          margin-bottom: 28px;
        }
        .section h2 {
          margin: 0 0 10px;
          font-size: 15px;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: var(--secondary-text-color, #7aa8b8);
        }
        /* ------------------------------------------------------------------ */
        /* Events strip                                                         */
        /* ------------------------------------------------------------------ */
        .events-block {
          padding: 16px 0 4px;
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
        .events-block label.check-row {
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
        .events-block label.check-row input {
          width: auto;
          flex-shrink: 0;
          margin: 0;
        }
        .events-block .btn-create,
        .events-block .btn-ghost {
          margin-top: 12px;
          width: 100%;
        }
        /* ------------------------------------------------------------------ */
        /* Shared button / layout                                               */
        /* ------------------------------------------------------------------ */
        .status-card {
          padding: 16px 0;
        }
        .status-line {
          font-size: 18px;
          margin: 0 0 6px;
        }
        .status-line strong {
          color: var(--primary-color, #00e5ff);
        }
        .meta {
          font-size: 13px;
          color: var(--secondary-text-color, #7aa8b8);
          margin: 0;
        }
        .toggle-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          padding: 14px 0;
          border-top: 1px solid var(--divider-color, #1f3a44);
        }
        .toggle-row:last-child {
          border-bottom: 1px solid var(--divider-color, #1f3a44);
        }
        .toggle-copy h3 {
          margin: 0 0 4px;
          font-size: 16px;
        }
        .toggle-copy p {
          margin: 0;
          font-size: 13px;
          color: var(--secondary-text-color, #7aa8b8);
        }
        .switch {
          position: relative;
          width: 48px;
          height: 28px;
          flex-shrink: 0;
        }
        .switch input {
          opacity: 0;
          width: 0;
          height: 0;
        }
        .slider {
          position: absolute;
          inset: 0;
          cursor: pointer;
          background: var(--disabled-color, #3a4a52);
          border-radius: 28px;
          transition: 0.2s;
        }
        .slider::before {
          content: "";
          position: absolute;
          height: 22px;
          width: 22px;
          left: 3px;
          top: 3px;
          background: #fff;
          border-radius: 50%;
          transition: 0.2s;
        }
        .switch input:checked + .slider {
          background: var(--primary-color, #00e5ff);
        }
        .switch input:checked + .slider::before {
          transform: translateX(20px);
        }
        .switch input:disabled + .slider {
          opacity: 0.45;
          cursor: not-allowed;
        }
        .gated {
          opacity: 0.55;
        }
        .gated .hint {
          font-size: 13px;
          color: var(--secondary-text-color, #7aa8b8);
          margin: 0 0 8px;
        }
        .actions {
          display: flex;
          gap: 10px;
          margin-top: 8px;
        }
        .catalog-block {
          padding-top: 4px;
        }
        .catalog-block label {
          display: block;
          font-size: 12px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: var(--secondary-text-color, #7aa8b8);
          margin: 12px 0 6px;
        }
        .catalog-block input[type="text"] {
          width: 100%;
          box-sizing: border-box;
          padding: 8px 10px;
          background: var(--secondary-background-color, #0d1418);
          color: var(--primary-text-color, #e8f6ff);
          border: 1px solid var(--divider-color, #1f3a44);
          border-radius: 6px;
          font: inherit;
        }
        .input-row {
          display: flex;
          gap: 8px;
          align-items: stretch;
        }
        .input-row input[type="text"] {
          flex: 1;
          min-width: 0;
        }
        .input-row .btn-ghost,
        .input-row .btn-create {
          margin-top: 0;
          white-space: nowrap;
        }
        .cat-card {
          padding: 14px 0;
          border-top: 1px solid var(--divider-color, #1f3a44);
        }
        .cat-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 8px;
        }
        .cat-head h3 {
          margin: 0;
          font-size: 16px;
        }
        .chip-row {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-bottom: 10px;
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
        .chip.default {
          background: var(--primary-color, #00e5ff);
          color: #041016;
          font-weight: 600;
        }
        .chip:disabled {
          opacity: 0.45;
          cursor: not-allowed;
        }
        .default-row {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 8px;
          margin-bottom: 10px;
        }
        .default-row label {
          margin: 0;
          text-transform: none;
          letter-spacing: 0;
          font-size: 13px;
          color: var(--primary-text-color, #e8f6ff);
        }
        .default-row select {
          flex: 1;
          min-width: 140px;
          box-sizing: border-box;
          padding: 6px 10px;
          background: var(--secondary-background-color, #0d1418);
          color: var(--primary-text-color, #e8f6ff);
          border: 1px solid var(--divider-color, #1f3a44);
          border-radius: 4px;
          font: inherit;
          font-size: 13px;
        }
        .small-btn {
          margin: 0;
          padding: 4px 10px;
          font-size: 12px;
          background: transparent;
          color: var(--primary-color, #00e5ff);
          border: 1px solid var(--primary-color, #00e5ff);
          border-radius: 4px;
          cursor: pointer;
          font: inherit;
        }
        .small-btn:disabled {
          opacity: 0.45;
          cursor: not-allowed;
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
        .small-btn:disabled {
          opacity: 0.45;
          cursor: not-allowed;
        }
      `
      ];
    }
    _formatErr(err) {
      if (err == null) return "unknown error";
      if (typeof err === "string") return err;
      const e = err;
      if (typeof e.error === "object" && e.error?.message) return e.error.message;
      if (typeof e.error === "string") return e.error;
      return e.message || e.code || JSON.stringify(err);
    }
    async _boot() {
      await this._refresh();
    }
    async _refresh() {
      this._busy = true;
      try {
        const result = await this.hass.callWS({
          type: "game_master/get_game_state"
        });
        this._state = result || {};
        this._feedback("Game state refreshed", "ok");
      } catch (err) {
        this._state = null;
        this._feedback("Could not load game state: " + this._formatErr(err), "err");
      } finally {
        this._busy = false;
      }
      await Promise.all([this._loadEvents(), this._loadCatalog()]);
    }
    // -------------------------------------------------------------------------
    // Events strip
    // -------------------------------------------------------------------------
    async _loadEvents() {
      try {
        const result = await this.hass.callWS({ type: "game_master/get_events" });
        this._events = result?.events ?? [];
        this._eventsReady = Boolean(result?.ready);
        this._eventsDetail = result?.detail || "";
        const activeId = String(this._state?.active_event?.id || "");
        if (activeId && !this._evSetActiveId) {
          this._evSetActiveId = activeId;
        }
      } catch (err) {
        this._events = [];
        this._eventsReady = false;
        this._eventsDetail = this._formatErr(err);
      }
    }
    _onEditEventPick(eventId) {
      this._evEditId = eventId;
      const ev = this._events.find((e) => String(e.id) === String(eventId));
      this._evEditName = ev?.name || "";
      this._evEditVenue = ev?.venue_name || "";
    }
    async _createEvent() {
      const name = this._evCreateName.trim();
      const venue = this._evCreateVenue.trim();
      const setActive = this._evCreateSetActive;
      if (!name) {
        this._feedback("Enter an event name", "warn");
        return;
      }
      this._busy = true;
      try {
        await this.hass.callService("game_master", "create_event", {
          name,
          venue_name: venue,
          set_active: setActive
        });
        this._feedback(
          setActive ? `Created and activated "${name}"` : `Created event "${name}"`,
          "ok"
        );
        this._evCreateName = "";
        this._evCreateVenue = "";
        await this._refresh();
      } catch (err) {
        this._feedback("Create event failed: " + this._formatErr(err), "err");
      } finally {
        this._busy = false;
      }
    }
    async _updateEvent() {
      if (!this._evEditId) {
        this._feedback("Pick an event to edit", "warn");
        return;
      }
      const payload = { event_id: this._evEditId };
      if (this._evEditName.trim()) payload.name = this._evEditName.trim();
      payload.venue_name = this._evEditVenue.trim() || "";
      this._busy = true;
      try {
        await this.hass.callService("game_master", "update_event", payload);
        this._feedback("Event updated", "ok");
        await this._loadEvents();
      } catch (err) {
        this._feedback("Update event failed: " + this._formatErr(err), "err");
      } finally {
        this._busy = false;
      }
    }
    async _setActiveEvent() {
      if (!this._evSetActiveId) {
        this._feedback("Pick an event to activate", "warn");
        return;
      }
      this._busy = true;
      try {
        await this.hass.callService("game_master", "set_active_event", {
          event_id: this._evSetActiveId
        });
        this._feedback("Active event saved", "ok");
        await this._refresh();
      } catch (err) {
        this._feedback("Set active failed: " + this._formatErr(err), "err");
      } finally {
        this._busy = false;
      }
    }
    _eventsSection() {
      const html = window.McPanel.html;
      const eventOptions = this._events.length > 0 ? this._events : [];
      const activeId = String(this._state?.active_event?.id || "");
      const activeName = (this._state?.active_event?.name || "").trim();
      return html`
      <section class="section">
        <h2>Events</h2>
        <div class="events-block">
          <p class="active-line">
            Active: <strong>${activeName || activeId || "None"}</strong>
          </p>
          ${!this._eventsReady && this._eventsDetail ? html`<p class="events-gate">${this._eventsDetail}</p>` : ""}
          <div class="mode-toggle" role="tablist" aria-label="Event action">
            <button
              type="button"
              class=${this._evMode === "create" ? "active" : ""}
              ?disabled=${this._busy}
              @click=${() => {
        this._evMode = "create";
      }}
            >
              Create
            </button>
            <button
              type="button"
              class=${this._evMode === "edit" ? "active" : ""}
              ?disabled=${this._busy}
              @click=${() => {
        this._evMode = "edit";
      }}
            >
              Edit
            </button>
            <button
              type="button"
              class=${this._evMode === "set" ? "active" : ""}
              ?disabled=${this._busy}
              @click=${() => {
        this._evMode = "set";
      }}
            >
              Set Active
            </button>
          </div>

          ${this._evMode === "create" ? html`
                <label for="ev-create-name">Name</label>
                <input
                  id="ev-create-name"
                  type="text"
                  ?disabled=${this._busy}
                  .value=${this._evCreateName}
                  @input=${(e) => {
        this._evCreateName = e.target.value;
      }}
                />
                <label for="ev-create-venue">Venue (optional)</label>
                <input
                  id="ev-create-venue"
                  type="text"
                  ?disabled=${this._busy}
                  .value=${this._evCreateVenue}
                  @input=${(e) => {
        this._evCreateVenue = e.target.value;
      }}
                />
                <label class="check-row">
                  <input
                    type="checkbox"
                    .checked=${this._evCreateSetActive}
                    ?disabled=${this._busy}
                    @change=${(e) => {
        this._evCreateSetActive = e.target.checked;
      }}
                  />
                  Set active after create
                </label>
                <button
                  class="btn-create"
                  ?disabled=${this._busy}
                  @click=${() => this._createEvent()}
                >
                  Create event
                </button>
              ` : this._evMode === "edit" ? html`
                  <label for="ev-edit-pick">Event</label>
                  <select
                    id="ev-edit-pick"
                    .value=${this._evEditId}
                    ?disabled=${this._busy || eventOptions.length === 0}
                    @change=${(e) => {
        this._onEditEventPick(e.target.value);
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
                    ?disabled=${this._busy}
                    .value=${this._evEditName}
                    @input=${(e) => {
        this._evEditName = e.target.value;
      }}
                  />
                  <label for="ev-edit-venue">Venue</label>
                  <input
                    id="ev-edit-venue"
                    type="text"
                    ?disabled=${this._busy}
                    .value=${this._evEditVenue}
                    @input=${(e) => {
        this._evEditVenue = e.target.value;
      }}
                  />
                  <button
                    class="btn-ghost"
                    ?disabled=${this._busy || !this._evEditId}
                    @click=${() => this._updateEvent()}
                  >
                    Save event
                  </button>
                ` : html`
                  <label for="ev-set-active">Event</label>
                  <select
                    id="ev-set-active"
                    .value=${this._evSetActiveId}
                    ?disabled=${this._busy || eventOptions.length === 0}
                    @change=${(e) => {
        this._evSetActiveId = e.target.value;
      }}
                  >
                    <option value="">
                      ${eventOptions.length ? "Select\u2026" : "No cached events yet \u2014 create one"}
                    </option>
                    ${eventOptions.map(
        (ev) => html`<option
                        value=${ev.id ?? ""}
                        ?selected=${String(ev.id ?? "") === activeId}
                      >
                        ${ev.name || ev.id}
                      </option>`
      )}
                  </select>
                  <button
                    class="btn-create"
                    ?disabled=${this._busy || !this._evSetActiveId}
                    @click=${() => this._setActiveEvent()}
                  >
                    Set active
                  </button>
                `}
        </div>
      </section>
    `;
    }
    // -------------------------------------------------------------------------
    // Affiliation catalog
    // -------------------------------------------------------------------------
    async _loadCatalog() {
      const prevEvent = this._catalog?.event_id || null;
      try {
        const result = await this.hass.callWS({
          type: "game_master/get_affiliation_catalog"
        });
        const next = {
          event_id: result?.event_id ?? null,
          categories: result?.categories ?? []
        };
        if (prevEvent && next.event_id && String(prevEvent) !== String(next.event_id)) {
          this._choiceDrafts = {};
          this._cancelRenames();
        }
        this._catalog = next;
      } catch (err) {
        this._catalog = emptyCatalog();
        this._feedback(
          "Could not load affiliation catalog: " + this._formatErr(err),
          "err"
        );
      }
    }
    _cancelRenames() {
      this._renameCatId = "";
      this._renameCatName = "";
      this._renameChoiceKey = "";
      this._renameChoiceName = "";
    }
    async _createCategory() {
      const name = this._catCreateName.trim();
      if (!name) {
        this._feedback("Enter a category name", "warn");
        return;
      }
      this._busy = true;
      try {
        await this.hass.callService("game_master", "create_affiliation_category", {
          name
        });
        this._catCreateName = "";
        await this._loadCatalog();
        this._feedback(`Created category ${name}`, "ok");
      } catch (err) {
        this._feedback("Create category failed: " + this._formatErr(err), "err");
      } finally {
        this._busy = false;
      }
    }
    async _saveCategoryRename() {
      const categoryId = this._renameCatId;
      const name = this._renameCatName.trim();
      if (!categoryId || !name) {
        this._feedback("Enter a category name", "warn");
        return;
      }
      this._busy = true;
      try {
        await this.hass.callService("game_master", "rename_affiliation_category", {
          category_id: categoryId,
          name
        });
        this._cancelRenames();
        await this._loadCatalog();
        this._feedback(`Renamed category to ${name}`, "ok");
      } catch (err) {
        this._feedback("Rename category failed: " + this._formatErr(err), "err");
      } finally {
        this._busy = false;
      }
    }
    async _createChoice(categoryId) {
      const name = (this._choiceDrafts[categoryId] || "").trim();
      if (!name) {
        this._feedback("Enter a choice name", "warn");
        return;
      }
      this._busy = true;
      try {
        await this.hass.callService("game_master", "create_affiliation", {
          category_id: categoryId,
          name
        });
        this._choiceDrafts = { ...this._choiceDrafts, [categoryId]: "" };
        await this._loadCatalog();
        this._feedback(`Created ${name}`, "ok");
      } catch (err) {
        this._feedback("Create affiliation failed: " + this._formatErr(err), "err");
      } finally {
        this._busy = false;
      }
    }
    async _saveChoiceRename(categoryId, affiliationId) {
      const name = this._renameChoiceName.trim();
      if (!name) {
        this._feedback("Enter a choice name", "warn");
        return;
      }
      this._busy = true;
      try {
        await this.hass.callService("game_master", "rename_affiliation", {
          category_id: categoryId,
          affiliation_id: affiliationId,
          name
        });
        this._cancelRenames();
        await this._loadCatalog();
        this._feedback(`Renamed to ${name}`, "ok");
      } catch (err) {
        this._feedback("Rename affiliation failed: " + this._formatErr(err), "err");
      } finally {
        this._busy = false;
      }
    }
    async _setDefault(categoryId, affiliationId) {
      this._busy = true;
      try {
        await this.hass.callService("game_master", "set_default_affiliation", {
          category_id: categoryId,
          affiliation_id: affiliationId
        });
        await this._loadCatalog();
        this._feedback(
          affiliationId ? "Default affiliation saved" : "Default affiliation cleared",
          "ok"
        );
      } catch (err) {
        this._feedback("Set default failed: " + this._formatErr(err), "err");
      } finally {
        this._busy = false;
      }
    }
    _catalogSection() {
      const html = window.McPanel.html;
      const cats = this._catalog.categories || [];
      const hasActive = Boolean(this._state?.active_event?.id);
      return html`
      <section class="section">
        <h2>Affiliation catalog</h2>
        <div class="catalog-block">
          <p class="meta">
            Categories and choices for the active event (cleared when the
            event changes). Set a default per category to prefill Registration
            when creating a player (HA-only; not written to Central). GBN
            selects from the catalog only.
          </p>
          <label for="cat-create">New category</label>
          <div class="input-row">
            <input
              id="cat-create"
              type="text"
              placeholder="e.g. Allegiance"
              .value=${this._catCreateName}
              ?disabled=${this._busy || !hasActive}
              @input=${(e) => {
        this._catCreateName = e.target.value;
      }}
              @keydown=${(e) => {
        if (e.key === "Enter") this._createCategory();
      }}
            />
            <button
              class="btn-ghost"
              ?disabled=${this._busy || !hasActive}
              @click=${() => this._createCategory()}
            >
              Add category
            </button>
          </div>
          ${!hasActive ? html`<p class="meta" style="margin-top:12px">
                Set an active event in the Events section above before editing the catalog.
              </p>` : ""}
          ${cats.length === 0 ? html`<p class="meta" style="margin-top:12px">
                No affiliation categories yet.
              </p>` : cats.map((cat) => this._categoryCard(cat))}
        </div>
      </section>
    `;
    }
    _categoryCard(cat) {
      const html = window.McPanel.html;
      const catId = String(cat.id);
      const renamingCat = this._renameCatId === catId;
      const choices = cat.affiliations || [];
      const defaultId = String(cat.default_affiliation_id || "");
      return html`
      <div class="cat-card">
        <div class="cat-head">
          ${renamingCat ? html`<div class="input-row" style="flex:1">
                <input
                  type="text"
                  .value=${this._renameCatName}
                  @input=${(e) => {
        this._renameCatName = e.target.value;
      }}
                  @keydown=${(e) => {
        if (e.key === "Enter") this._saveCategoryRename();
        if (e.key === "Escape") this._cancelRenames();
      }}
                />
                <button
                  class="btn-create"
                  ?disabled=${this._busy}
                  @click=${() => this._saveCategoryRename()}
                >
                  Save
                </button>
                <button class="btn-ghost" @click=${() => this._cancelRenames()}>
                  Cancel
                </button>
              </div>` : html`<h3>${cat.name || cat.id}</h3>
                <button
                  class="small-btn"
                  ?disabled=${this._busy}
                  @click=${() => {
        this._cancelRenames();
        this._renameCatId = catId;
        this._renameCatName = cat.name || "";
      }}
                >
                  Rename
                </button>`}
        </div>
        ${choices.length === 0 ? html`<p class="meta" style="margin-bottom:10px">No choices yet.</p>` : html`<div class="chip-row">
              ${choices.map((c) => {
        const key = `${catId}:${c.id}`;
        const isDefault = defaultId === String(c.id);
        if (this._renameChoiceKey === key) {
          return html`<div class="input-row" style="width:100%">
                    <input
                      type="text"
                      .value=${this._renameChoiceName}
                      @input=${(e) => {
            this._renameChoiceName = e.target.value;
          }}
                      @keydown=${(e) => {
            if (e.key === "Enter")
              this._saveChoiceRename(catId, String(c.id));
            if (e.key === "Escape") this._cancelRenames();
          }}
                    />
                    <button
                      class="btn-create"
                      ?disabled=${this._busy}
                      @click=${() => this._saveChoiceRename(catId, String(c.id))}
                    >
                      Save
                    </button>
                    <button class="btn-ghost" @click=${() => this._cancelRenames()}>
                      Cancel
                    </button>
                  </div>`;
        }
        return html`<button
                  type="button"
                  class="chip ${isDefault ? "default" : ""}"
                  title=${isDefault ? "Default for new players \u2014 click to rename" : "Click to rename"}
                  ?disabled=${this._busy}
                  @click=${() => {
          this._cancelRenames();
          this._renameChoiceKey = key;
          this._renameChoiceName = c.name || "";
        }}
                >
                  ${c.name}${isDefault ? " \u2605" : ""}
                </button>`;
      })}
            </div>
            <div class="default-row">
              <label for=${`def-${catId}`}>Default for new players</label>
              <select
                id=${`def-${catId}`}
                .value=${defaultId}
                ?disabled=${this._busy}
                @change=${(e) => {
        this._setDefault(
          catId,
          e.target.value
        );
      }}
              >
                <option value="">None</option>
                ${choices.map(
        (c) => html`<option
                    value=${c.id}
                    ?selected=${defaultId === String(c.id)}
                  >
                    ${c.name}
                  </option>`
      )}
              </select>
            </div>`}
        <div class="input-row">
          <input
            type="text"
            placeholder="New choice, e.g. Helix Industries"
            .value=${this._choiceDrafts[catId] || ""}
            ?disabled=${this._busy}
            @input=${(e) => {
        this._choiceDrafts = {
          ...this._choiceDrafts,
          [catId]: e.target.value
        };
      }}
            @keydown=${(e) => {
        if (e.key === "Enter") this._createChoice(catId);
      }}
          />
          <button
            class="btn-ghost"
            ?disabled=${this._busy}
            @click=${() => this._createChoice(catId)}
          >
            Add choice
          </button>
        </div>
      </div>
    `;
    }
    // -------------------------------------------------------------------------
    // Scoring toggles
    // -------------------------------------------------------------------------
    async _setScoring(enabled) {
      this._busy = true;
      try {
        await this.hass.callWS({
          type: "game_master/set_scoring",
          enabled
        });
        this._feedback(enabled ? "Game live \u2014 scoring on" : "Scoring off", "ok");
        await this._refresh();
      } catch (err) {
        this._feedback("Scoring update failed: " + this._formatErr(err), "err");
        this._busy = false;
      }
    }
    async _setDelayed(enabled) {
      this._busy = true;
      try {
        await this.hass.callWS({
          type: "game_master/set_delayed_scores",
          enabled
        });
        this._feedback(
          enabled ? "Delayed scores accepted" : "Delayed scores blocked",
          "ok"
        );
        await this._refresh();
      } catch (err) {
        this._feedback("Delayed scores update failed: " + this._formatErr(err), "err");
        this._busy = false;
      }
    }
    _activeLabel() {
      const ev = this._state?.active_event;
      if (!ev) return "None \u2014 create or set an active event in the Events section";
      const name = (ev.name || "").trim();
      const venue = (ev.venue_name || "").trim();
      if (name && venue) return `${name} \xB7 ${venue}`;
      return name || ev.id || "Unknown event";
    }
    _formatTime(value) {
      if (!value) return "";
      try {
        const d = new Date(value);
        if (Number.isNaN(d.getTime())) return value;
        return d.toLocaleString();
      } catch {
        return value;
      }
    }
    render() {
      const html = window.McPanel.html;
      const state = this._state;
      const scoringOn = Boolean(state?.scoring?.enabled);
      const delayedOn = state?.accepting_delayed_scores !== false && state != null ? Boolean(state.accepting_delayed_scores) : false;
      const hasActive = Boolean(state?.active_event?.id);
      const canToggle = hasActive && !this._busy;
      return html`
      <div class="wrap">
        <header class="page-header">
          <h1>Game Master</h1>
          <p class="sub">
            Manage events and control live gameplay for the active event.
          </p>
        </header>

        ${this._eventsSection()}

        <section class="section">
          <h2>Active event</h2>
          <div class="status-card">
            <p class="status-line">
              <strong>${this._activeLabel()}</strong>
            </p>
            <p class="meta">
              Server time:
              ${this._formatTime(state?.server_time_utc) || "\u2014"}
              ${scoringOn && state?.scoring?.started_at ? html` · Scoring since
                  ${this._formatTime(state.scoring.started_at)}` : ""}
            </p>
          </div>
          <div class="actions">
            <button
              class="btn-ghost"
              ?disabled=${this._busy}
              @click=${() => this._refresh()}
            >
              Refresh
            </button>
          </div>
        </section>

        <section class="section">
          <h2>Gameplay</h2>
          <div class="toggle-row">
            <div class="toggle-copy">
              <h3>Game live</h3>
              <p>Turns scoring on or off for the active event.</p>
            </div>
            <label class="switch">
              <input
                type="checkbox"
                .checked=${scoringOn}
                ?disabled=${!canToggle}
                @change=${(e) => {
        const on = e.target.checked;
        this._setScoring(on);
      }}
              />
              <span class="slider"></span>
            </label>
          </div>
          <div class="toggle-row">
            <div class="toggle-copy">
              <h3>Accept delayed scores</h3>
              <p>
                When off, matches from closed scoring periods are saved as
                delayed_scores_disabled.
              </p>
            </div>
            <label class="switch">
              <input
                type="checkbox"
                .checked=${delayedOn}
                ?disabled=${!canToggle}
                @change=${(e) => {
        const on = e.target.checked;
        this._setDelayed(on);
      }}
              />
              <span class="slider"></span>
            </label>
          </div>
          ${!hasActive ? html`<p class="meta" style="margin-top:12px">
                Set an active event above before toggling gameplay.
              </p>` : ""}
        </section>

        ${this._catalogSection()}

        <section class="section gated">
          <h2>Hours of operation</h2>
          <p class="hint">Waiting on Central — venue open/close windows.</p>
          <button class="btn-ghost" disabled>Configure hours</button>
        </section>

        <section class="section gated">
          <h2>Special events</h2>
          <p class="hint">Waiting on Central — trigger named gameplay specials.</p>
          <button class="btn-ghost" disabled>Trigger special</button>
        </section>

        ${this._feedbackTemplate()}
      </div>
    `;
    }
  };
  customElements.define("game-master-panel", GameMasterPanel);
})();
