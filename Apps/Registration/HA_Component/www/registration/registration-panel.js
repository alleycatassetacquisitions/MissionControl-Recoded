"use strict";
(() => {
  // src/panels/registration-panel.ts
  var RegistrationPanel = class extends window.McPanel.Base {
    static get properties() {
      return {
        ...super.properties,
        _roster: { state: true },
        _editingId: { state: true },
        _postersByPlayer: { state: true },
        _fName: { state: true },
        _fRole: { state: true },
        _fNeocorp: { state: true },
        _fFaction: { state: true },
        _fNeoId: { state: true }
      };
    }
    constructor() {
      super();
      this._roster = [];
      this._editingId = null;
      this._postersByPlayer = {};
      this._fName = "";
      this._fRole = "hunter";
      this._fNeocorp = "freelancer";
      this._fFaction = "";
      this._fNeoId = "";
    }
    static get styles() {
      const base = super.styles;
      const baseArr = Array.isArray(base) ? base : base ? [base] : [];
      return [
        ...baseArr,
        window.McPanel.css`
        .roster-table {
          width: 100%;
          border-collapse: collapse;
          margin-top: 12px;
        }
        .roster-table th,
        .roster-table td {
          padding: 8px 12px;
          text-align: left;
          border-bottom: 1px solid var(--divider-color, #2a3555);
        }
        .roster-table th {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--secondary-text-color);
        }
        .form-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
          gap: 12px 16px;
          align-items: end;
          margin-top: 8px;
        }
        .field {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .field label {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: var(--secondary-text-color);
        }
        .field-actions {
          display: flex;
          gap: 8px;
          align-items: end;
        }
        .count-badge {
          font-size: 0.85rem;
          color: var(--secondary-text-color);
          margin-left: 8px;
        }
        .actions-cell {
          white-space: nowrap;
        }
        .poster-cell {
          min-width: 88px;
        }
        .poster-thumb {
          width: 64px;
          height: 36px;
          object-fit: cover;
          border-radius: 4px;
          background: #111;
          vertical-align: middle;
        }
        .poster-missing {
          color: var(--secondary-text-color);
          font-size: 0.8rem;
        }
      `
      ];
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
      </a>`;
      }
      return html`<a class="btn-link" href=${href} target="_blank" rel="noopener"
      >open</a
    >`;
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
        this._feedback("Name is required.", "warn");
        return;
      }
      try {
        if (this._editingId) {
          await this.hass.callService("registration", "update_player", {
            player_id: this._editingId,
            ...payload
          });
          this._feedback("Player updated.", "ok");
        } else {
          await this.hass.callService("registration", "register_player", payload);
          this._feedback("Player registered.", "ok");
        }
        this._clearForm();
        await this.hass.callService("registration", "sync_now", {});
        await this._loadRoster();
      } catch (err) {
        this._feedback(
          (this._editingId ? "Update failed: " : "Registration failed: ") + this._formatErr(err),
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
      const loadFailed = !this.hass || this._feedbackKind === "err" && String(this._feedbackMsg).includes("Could not load roster");
      return html`
      <div class="wrap">
        <header class="page-header">
          <h1>
            Registration
            <span class="count-badge"
              >(${count} player${count === 1 ? "" : "s"})</span
            >
          </h1>
          <div class="header-actions">
            ${this._feedbackTemplate()}
            <button class="btn btn-secondary" @click=${() => this._syncNow()}>
              Sync Now
            </button>
          </div>
        </header>

        <div id="cards">
          <div class="card">
            <div class="card-header">
              ${editing ? "Update Player" : "Register Player"}
            </div>
            <div class="card-body">
              <div class="form-grid">
                <div class="field">
                  <label for="f-name">Name</label>
                  <input
                    id="f-name"
                    type="text"
                    autocomplete="off"
                    .value=${this._fName}
                    @input=${(e) => {
        this._fName = e.target.value;
      }}
                  />
                </div>
                <div class="field">
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
                </div>
                <div class="field">
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
                    <option value="reboot">Reboot</option>
                    <option value="helix">Helix</option>
                  </select>
                </div>
                <div class="field">
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
                </div>
                <div class="field">
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
                </div>
                <div class="field-actions">
                  <button
                    class="btn btn-primary"
                    @click=${() => this._savePlayer()}
                  >
                    ${editing ? "Update" : "Register"}
                  </button>
                  <button
                    class="btn btn-secondary"
                    ?hidden=${!editing}
                    @click=${() => this._clearForm()}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div class="card" style="margin-top:16px">
            <div class="card-header">Current Roster</div>
            <div class="card-body">
              ${loadFailed && count === 0 ? html`<p style="color:var(--error-color,#f44336)">
                    Could not load roster.
                  </p>` : count === 0 ? html`<p style="color:var(--secondary-text-color)">
                      No players registered yet.
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
                          ${this._roster.map(
        (p) => html`
                              <tr>
                                <td>${p.id ?? ""}</td>
                                <td>${p.name ?? ""}</td>
                                <td>${p.role ?? ""}</td>
                                <td>${this._titleCaseNeo(p.neocorp)}</td>
                                <td>${p.faction ?? ""}</td>
                                <td>${p.neo_id ?? ""}</td>
                                <td class="poster-cell">
                                  ${this._posterCell(p)}
                                </td>
                                <td class="actions-cell">
                                  <button
                                    class="btn btn-link"
                                    @click=${() => this._startEdit(p)}
                                  >
                                    Edit
                                  </button>
                                  <button
                                    class="btn btn-link"
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
      </div>
    `;
    }
  };
  customElements.define("registration-panel", RegistrationPanel);
})();
//# sourceMappingURL=registration-panel.js.map
