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
        .chip:disabled {
          opacity: 0.45;
          cursor: not-allowed;
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
      await this._loadCatalog();
    }
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
            event changes). Registration assigns them to players; GBN only
            selects from them.
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
                Set an active event in Registration before editing the catalog.
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
                  class="chip"
                  title="Click to rename"
                  ?disabled=${this._busy}
                  @click=${() => {
          this._cancelRenames();
          this._renameChoiceKey = key;
          this._renameChoiceName = c.name || "";
        }}
                >
                  ${c.name}
                </button>`;
      })}
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
      if (!ev) return "None \u2014 select an event in Registration";
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
            Control live gameplay for the active event. Change which event is
            active in Registration.
          </p>
        </header>

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
                Set an active event in Registration before toggling gameplay.
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
//# sourceMappingURL=game-master-panel.js.map
