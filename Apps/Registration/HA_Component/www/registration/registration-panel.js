"use strict";
(() => {
  // src/panels/registration-panel.ts
  var RegistrationPanel = class extends window.McPanel.Base {
    constructor() {
      super();
      this._checkTimer = null;
      this._roster = [];
      this._editingId = null;
      this._postersByPlayer = {};
      this._search = "";
      this._nameStatus = "";
      this._fName = "";
      this._fRole = "hunter";
      this._fNeocorp = "freelancer";
      this._fFaction = "";
      this._fNeoId = "";
    }
    static get properties() {
      return {
        ...super.properties,
        _roster: { state: true },
        _editingId: { state: true },
        _postersByPlayer: { state: true },
        _search: { state: true },
        _nameStatus: { state: true },
        _fName: { state: true },
        _fRole: { state: true },
        _fNeocorp: { state: true },
        _fFaction: { state: true },
        _fNeoId: { state: true }
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
          align-items: unset;
          gap: 0;
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
        .layout {
          display: grid;
          grid-template-columns: 340px 1fr;
          min-height: calc(100vh - 72px);
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
        .btn-danger-outline {
          background: transparent;
          color: #e24b4a;
          border: 1px solid #e24b4a;
          border-radius: 6px;
          padding: 10px 16px;
          cursor: pointer;
          font: inherit;
        }
        .feedback {
          min-height: 20px;
          font-size: 13px;
          margin-top: 12px;
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
        .roster-table tr.selected {
          background: rgba(0, 229, 255, 0.07);
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
        .edit-btn:hover,
        .delete-btn:hover {
          background: rgba(0, 229, 255, 0.1);
        }
        .delete-btn {
          color: #e24b4a;
          border-color: #e24b4a;
          margin-left: 6px;
        }
        .delete-btn:hover {
          background: rgba(226, 75, 74, 0.1);
        }
        .poster-cell {
          min-width: 88px;
        }
        .poster-cell a {
          color: var(--primary-color, #00e5ff);
          text-decoration: none;
        }
        .poster-cell a:hover {
          text-decoration: underline;
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
      return e.message || e.error || e.code || JSON.stringify(err);
    }
    _titleCaseNeo(value) {
      const v = (value || "").toString().trim().toLowerCase();
      if (!v) return "";
      return v.charAt(0).toUpperCase() + v.slice(1);
    }
    _formPayload() {
      return {
        name: this._fName.trim(),
        role: this._fRole,
        neocorp: this._fNeocorp,
        faction: this._fFaction.trim(),
        neo_id: this._fNeoId.trim()
      };
    }
    _clearForm() {
      this._editingId = null;
      this._fName = "";
      this._fRole = "hunter";
      this._fNeocorp = "freelancer";
      this._fFaction = "";
      this._fNeoId = "";
      this._nameStatus = "";
      if (this._checkTimer) {
        clearTimeout(this._checkTimer);
        this._checkTimer = null;
      }
    }
    _startEdit(player) {
      this._editingId = player.id ?? null;
      this._fName = player.name || "";
      const role = (player.role || "hunter").toLowerCase();
      this._fRole = role === "bounty" ? "bounty" : "hunter";
      const neo = (player.neocorp || "freelancer").toLowerCase();
      this._fNeocorp = ["freelancer", "endline", "reboot", "helix"].includes(neo) ? neo : "freelancer";
      this._fFaction = player.faction || "";
      this._fNeoId = player.neo_id || "";
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
      const clash = this._roster.find((p) => {
        if ((p.name || "").trim().toLowerCase() !== needle) return false;
        if (this._editingId != null && String(p.id) === String(this._editingId)) {
          return false;
        }
        return true;
      });
      this._nameStatus = clash ? "taken" : "available";
    }
    _filteredRoster() {
      const term = this._search.trim().toLowerCase();
      if (!term) return this._roster;
      return this._roster.filter(
        (p) => String(p.id ?? "").toLowerCase().includes(term) || String(p.name ?? "").toLowerCase().includes(term)
      );
    }
    async _boot() {
      await this._loadRoster();
      await this._loadPosters();
    }
    async _loadPosters() {
      this._postersByPlayer = {};
      try {
        const headers = { "cache-control": "no-store" };
        if (this._token()) headers.Authorization = `Bearer ${this._token()}`;
        const resp = await fetch("/api/gbn/proxy/api/posters", {
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
          await this._loadRoster();
          await this._loadPosters();
        }, 1500);
      } catch (err) {
        this._feedback("Sync failed: " + this._formatErr(err), "err");
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
      try {
        if (this._editingId) {
          await this.hass.callService("registration", "update_player", {
            player_id: this._editingId,
            ...payload
          });
          this._feedback(`Updated ${payload.name}`, "ok");
        } else {
          await this.hass.callService("registration", "register_player", payload);
          this._feedback(`Registered ${payload.name}`, "ok");
        }
        this._clearForm();
        await this.hass.callService("registration", "sync_now", {});
        await this._loadRoster();
      } catch (err) {
        this._feedback(
          (this._editingId ? "Update failed: " : "Register failed: ") + this._formatErr(err),
          "err"
        );
      }
    }
    async _deletePlayer(player) {
      if (!player?.id) return;
      if (!window.confirm(`Delete player "${player.name || player.id}"?`)) return;
      try {
        await this.hass.callService("registration", "delete_player", {
          player_id: player.id
        });
        this._feedback("Player deleted.", "ok");
        if (this._editingId === player.id) this._clearForm();
        await this.hass.callService("registration", "sync_now", {});
        await this._loadRoster();
      } catch (err) {
        this._feedback("Delete failed: " + this._formatErr(err), "err");
      }
    }
    render() {
      const html = window.McPanel.html;
      const count = this._roster.length;
      const editing = this._editingId != null;
      const filtered = this._filteredRoster();
      const loadFailed = !this.hass || this._feedbackKind === "err" && String(this._feedbackMsg).includes("Could not load roster");
      return html`
      <div class="wrap">
        <header class="page-header">
          <div class="header-row">
            <div>
              <h1>Registration</h1>
              <p class="sub">
                Player roster and registration via Mission Control
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
            <h2 class="form-title">
              ${editing ? "Edit Player Registration" : "Register player"}
            </h2>
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
            <label for="f-role">Role</label>
            <select
              id="f-role"
              .value=${this._fRole}
              @change=${(e) => {
        this._fRole = e.target.value;
      }}
            >
              <option value="hunter">Hunter</option>
              <option value="bounty">Bounty</option>
            </select>
            <label for="f-neocorp">NeoCorp</label>
            <select
              id="f-neocorp"
              .value=${this._fNeocorp}
              @change=${(e) => {
        this._fNeocorp = e.target.value;
      }}
            >
              <option value="freelancer">Freelancer</option>
              <option value="endline">Endline</option>
              <option value="helix">Helix</option>
              <option value="reboot">Reboot</option>
            </select>
            <label for="f-faction">Faction</label>
            <input
              id="f-faction"
              type="text"
              autocomplete="off"
              .value=${this._fFaction}
              @input=${(e) => {
        this._fFaction = e.target.value;
      }}
            />
            <label for="f-neo-id">Neo ID</label>
            <input
              id="f-neo-id"
              type="text"
              autocomplete="off"
              .value=${this._fNeoId}
              @input=${(e) => {
        this._fNeoId = e.target.value;
      }}
            />
            <div class="form-actions">
              ${editing ? html`
                    <button class="btn-create" @click=${() => this._savePlayer()}>
                      Save changes
                    </button>
                    <button
                      class="btn-danger-outline"
                      @click=${() => this._clearForm()}
                    >
                      Cancel
                    </button>
                  ` : html`
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
            <div class="search-row">
              <input
                id="search"
                type="search"
                placeholder="Search by name or ID…"
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
                          <th>ID</th>
                          <th>Name</th>
                          <th>Role</th>
                          <th>NeoCorp</th>
                          <th>Faction</th>
                          <th>Neo ID</th>
                          <th>Poster</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        ${filtered.map(
        (p) => html`
                            <tr
                              class=${this._editingId != null && String(this._editingId) === String(p.id) ? "selected" : ""}
                            >
                              <td>${p.id ?? ""}</td>
                              <td>${p.name ?? ""}</td>
                              <td>${p.role ?? ""}</td>
                              <td>${this._titleCaseNeo(p.neocorp)}</td>
                              <td>${p.faction ?? ""}</td>
                              <td>${p.neo_id ?? ""}</td>
                              <td class="poster-cell">${this._posterCell(p)}</td>
                              <td class="actions-cell">
                                <button
                                  class="edit-btn"
                                  @click=${() => this._startEdit(p)}
                                >
                                  Edit
                                </button>
                                <button
                                  class="delete-btn"
                                  @click=${() => this._deletePlayer(p)}
                                >
                                  Delete
                                </button>
                              </td>
                            </tr>
                          `
      )}
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
