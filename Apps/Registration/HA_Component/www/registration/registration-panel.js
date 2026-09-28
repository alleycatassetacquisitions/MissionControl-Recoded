/**
 * Registration panel — Home Assistant sidebar panel for player management.
 *
 * Design contract:
 *  - Extends McPanelBase from shared_libraries/mc-panel.js.
 *  - ALL data reads and writes go through hass.callWS / hass.callService.
 *    Zero direct fetch() calls to MCS or any LAN IP.
 *
 * Websocket:
 *  - registration/get_roster → coordinator-cached roster
 *
 * HA services:
 *  - registration.sync_now
 *  - registration.register_player
 *  - registration.update_player
 *  - registration.delete_player
 */

class RegistrationPanel extends window.McPanel.Base {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._roster = [];
    this._editingId = null;
    this._postersByPlayer = {};
  }

  set hass(hass) {
    super.hass = hass;
  }
  get hass() {
    return super.hass;
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        ${window.McPanel.Base.sharedStyles()}
        .roster-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
        .roster-table th,
        .roster-table td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--divider-color, #2a3555); }
        .roster-table th { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--secondary-text-color); }
        .form-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
          gap: 12px 16px;
          align-items: end;
          margin-top: 8px;
        }
        .field { display: flex; flex-direction: column; gap: 4px; }
        .field label {
          font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em;
          color: var(--secondary-text-color);
        }
        .field input, .field select {
          width: 100%; padding: 8px; border-radius: 6px; box-sizing: border-box;
          background: var(--input-background, #1e2a45); border: 1px solid var(--divider-color, #2a3555);
          color: var(--primary-text-color); font-size: 0.9rem;
        }
        .field-actions { display: flex; gap: 8px; align-items: end; }
        .btn { padding: 8px 18px; border-radius: 6px; border: none; cursor: pointer; font-size: 0.9rem; }
        .btn-primary { background: var(--primary-color, #3d85c8); color: #fff; }
        .btn-secondary { background: var(--secondary-background-color, #1e2a45); color: var(--primary-text-color); }
        .btn-danger { background: transparent; color: var(--error-color, #f44336); border: 1px solid var(--error-color, #f44336); }
        .btn-link { background: transparent; color: var(--primary-color, #3d85c8); padding: 4px 8px; }
        .count-badge { font-size: 0.85rem; color: var(--secondary-text-color); margin-left: 8px; }
        .actions-cell { white-space: nowrap; }
        .poster-cell { min-width: 88px; }
        .poster-thumb {
          width: 64px; height: 36px; object-fit: cover; border-radius: 4px;
          background: #111; vertical-align: middle;
        }
        .poster-missing { color: var(--secondary-text-color); font-size: 0.8rem; }
      </style>

      <div class="wrap">
        <header class="page-header">
          <h1>Registration
            <span class="count-badge" id="count"></span>
          </h1>
          <div class="header-actions">
            <span id="feedback" class="feedback"></span>
            <button class="btn btn-secondary" id="sync-btn">Sync Now</button>
          </div>
        </header>

        <div id="cards">
          <div class="card">
            <div class="card-header" id="form-title">Register Player</div>
            <div class="card-body">
              <div class="form-grid">
                <div class="field">
                  <label for="f-name">Name</label>
                  <input id="f-name" type="text" autocomplete="off" />
                </div>
                <div class="field">
                  <label for="f-role">Role</label>
                  <select id="f-role">
                    <option value="hunter">Hunter</option>
                    <option value="bounty">Bounty</option>
                  </select>
                </div>
                <div class="field">
                  <label for="f-neocorp">NeoCorp</label>
                  <select id="f-neocorp">
                    <option value="freelancer" selected>Freelancer</option>
                    <option value="endline">Endline</option>
                    <option value="reboot">Reboot</option>
                    <option value="helix">Helix</option>
                  </select>
                </div>
                <div class="field">
                  <label for="f-faction">Faction</label>
                  <input id="f-faction" type="text" autocomplete="off" />
                </div>
                <div class="field">
                  <label for="f-neo-id">Neo ID</label>
                  <input id="f-neo-id" type="text" autocomplete="off" />
                </div>
                <div class="field-actions">
                  <button class="btn btn-primary" id="save-btn">Register</button>
                  <button class="btn btn-secondary" id="cancel-btn" hidden>Cancel</button>
                </div>
              </div>
            </div>
          </div>

          <div class="card" style="margin-top:16px">
            <div class="card-header">Current Roster</div>
            <div class="card-body" id="roster-body">
              <p style="color:var(--secondary-text-color)">Loading…</p>
            </div>
          </div>
        </div>
      </div>`;
  }

  async _boot() {
    this.shadowRoot
      .getElementById("sync-btn")
      .addEventListener("click", () => this._syncNow());
    this.shadowRoot
      .getElementById("save-btn")
      .addEventListener("click", () => this._savePlayer());
    this.shadowRoot
      .getElementById("cancel-btn")
      .addEventListener("click", () => this._clearForm());

    await this._loadRoster();
    await this._loadPosters();
  }

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  _token() {
    return this._hass?.auth?.data?.access_token || "";
  }

  async _loadPosters() {
    this._postersByPlayer = {};
    try {
      const headers = { "cache-control": "no-store" };
      if (this._token()) headers.Authorization = `Bearer ${this._token()}`;
      const resp = await fetch("/api/gbn/proxy/api/posters", {
        headers,
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!resp.ok) return;
      const list = await resp.json();
      if (!Array.isArray(list)) return;
      for (const p of list) {
        const id = String(p.player_id || "");
        if (id) this._postersByPlayer[id] = p;
      }
      this._renderRoster();
    } catch (_) {
      // GBN may not be installed yet — roster still works without posters.
    }
  }

  _formatErr(err) {
    if (err == null) return "unknown error";
    if (typeof err === "string") return err;
    return err.message || err.error || err.code || JSON.stringify(err);
  }

  _titleCaseNeo(value) {
    const v = (value || "").toString().trim().toLowerCase();
    if (!v) return "";
    return v.charAt(0).toUpperCase() + v.slice(1);
  }

  _formPayload() {
    return {
      name: this.shadowRoot.getElementById("f-name").value.trim(),
      role: this.shadowRoot.getElementById("f-role").value,
      neocorp: this.shadowRoot.getElementById("f-neocorp").value,
      faction: this.shadowRoot.getElementById("f-faction").value.trim(),
      neo_id: this.shadowRoot.getElementById("f-neo-id").value.trim(),
    };
  }

  _clearForm() {
    this._editingId = null;
    this.shadowRoot.getElementById("f-name").value = "";
    this.shadowRoot.getElementById("f-role").value = "hunter";
    this.shadowRoot.getElementById("f-neocorp").value = "freelancer";
    this.shadowRoot.getElementById("f-faction").value = "";
    this.shadowRoot.getElementById("f-neo-id").value = "";
    this.shadowRoot.getElementById("form-title").textContent = "Register Player";
    this.shadowRoot.getElementById("save-btn").textContent = "Register";
    this.shadowRoot.getElementById("cancel-btn").hidden = true;
  }

  _startEdit(player) {
    this._editingId = player.id;
    this.shadowRoot.getElementById("f-name").value = player.name || "";
    const role = (player.role || "hunter").toLowerCase();
    this.shadowRoot.getElementById("f-role").value =
      role === "bounty" ? "bounty" : "hunter";
    const neo = (player.neocorp || "freelancer").toLowerCase();
    const neoSelect = this.shadowRoot.getElementById("f-neocorp");
    neoSelect.value = ["freelancer", "endline", "reboot", "helix"].includes(neo)
      ? neo
      : "freelancer";
    this.shadowRoot.getElementById("f-faction").value = player.faction || "";
    this.shadowRoot.getElementById("f-neo-id").value = player.neo_id || "";
    this.shadowRoot.getElementById("form-title").textContent = "Update Player";
    this.shadowRoot.getElementById("save-btn").textContent = "Update";
    this.shadowRoot.getElementById("cancel-btn").hidden = false;
  }

  // -------------------------------------------------------------------------
  // Data
  // -------------------------------------------------------------------------

  async _loadRoster() {
    try {
      const result = await this._hass.callWS({ type: "registration/get_roster" });
      this._roster = result?.players ?? [];
      this._renderRoster();
    } catch (err) {
      const body = this.shadowRoot.getElementById("roster-body");
      if (body) {
        body.innerHTML = `<p style="color:var(--error-color,#f44336)">Could not load roster.</p>`;
      }
      this._feedback("Could not load roster: " + this._formatErr(err), "err");
    }
  }

  _renderRoster() {
    const count = this._roster.length;
    const badge = this.shadowRoot.getElementById("count");
    if (badge) badge.textContent = `(${count} player${count === 1 ? "" : "s"})`;

    const body = this.shadowRoot.getElementById("roster-body");
    if (!body) return;

    if (count === 0) {
      body.innerHTML = `<p style="color:var(--secondary-text-color)">No players registered yet.</p>`;
      return;
    }

    body.innerHTML = `
      <table class="roster-table">
        <thead>
          <tr>
            <th>ID</th><th>Name</th><th>Role</th><th>NeoCorp</th><th>Faction</th><th>Neo ID</th><th>Poster</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${this._roster
            .map(
              (p, idx) => `
            <tr data-idx="${idx}">
              <td>${this._esc(p.id ?? "")}</td>
              <td>${this._esc(p.name ?? "")}</td>
              <td>${this._esc(p.role ?? "")}</td>
              <td>${this._esc(this._titleCaseNeo(p.neocorp))}</td>
              <td>${this._esc(p.faction ?? "")}</td>
              <td>${this._esc(p.neo_id ?? "")}</td>
              <td class="poster-cell">${this._posterCell(p)}</td>
              <td class="actions-cell">
                <button class="btn btn-link edit-btn" data-idx="${idx}">Edit</button>
                <button class="btn btn-link delete-btn" data-idx="${idx}">Delete</button>
              </td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;

    body.querySelectorAll(".edit-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = this._roster[Number(btn.dataset.idx)];
        if (p) this._startEdit(p);
      });
    });
    body.querySelectorAll(".delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const p = this._roster[Number(btn.dataset.idx)];
        if (p) this._deletePlayer(p);
      });
    });
  }

  _posterCell(player) {
    const poster = this._postersByPlayer[String(player.id)] || null;
    if (!poster) {
      return `<span class="poster-missing">—</span>`;
    }
    const href = this._esc(poster.poster_url || "");
    const video = this._esc(poster.video_url || "");
    if (video) {
      return `<a href="${href}" target="_blank" rel="noopener" title="Open poster">
        <video class="poster-thumb" src="${video}" muted playsinline></video>
      </a>`;
    }
    return `<a class="btn-link" href="${href}" target="_blank" rel="noopener">open</a>`;
  }

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------

  async _syncNow() {
    try {
      await this._hass.callService("registration", "sync_now", {});
      this._feedback("Syncing…", "ok");
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
        await this._hass.callService("registration", "update_player", {
          player_id: this._editingId,
          ...payload,
        });
        this._feedback("Player updated.", "ok");
      } else {
        await this._hass.callService("registration", "register_player", payload);
        this._feedback("Player registered.", "ok");
      }
      this._clearForm();
      await this._hass.callService("registration", "sync_now", {});
      await this._loadRoster();
    } catch (err) {
      this._feedback(
        (this._editingId ? "Update failed: " : "Registration failed: ") +
          this._formatErr(err),
        "err"
      );
    }
  }

  async _deletePlayer(player) {
    if (!player?.id) return;
    if (!window.confirm(`Delete player "${player.name || player.id}"?`)) return;
    try {
      await this._hass.callService("registration", "delete_player", {
        player_id: player.id,
      });
      this._feedback("Player deleted.", "ok");
      if (this._editingId === player.id) this._clearForm();
      await this._hass.callService("registration", "sync_now", {});
      await this._loadRoster();
    } catch (err) {
      this._feedback("Delete failed: " + this._formatErr(err), "err");
    }
  }
}

customElements.define("registration-panel", RegistrationPanel);
