/**
 * Registration panel — Home Assistant sidebar panel for player management.
 *
 * Design contract:
 *  - Extends McPanelBase from shared_libraries/mc-panel.js.
 *  - ALL data reads and writes go through hass.callWS / hass.callService.
 *    Zero direct fetch() calls to MCS or any LAN IP.
 *  - The roster sensor (sensor.registration_roster_count) is the live source
 *    of truth for the player list shown here.
 *
 * Websocket calls used:
 *  - registration/get_roster   → full player list from coordinator cache
 *  - registration/register_player → POST a new player via HA service
 *
 * HA services called:
 *  - registration.sync_now        → force coordinator refresh
 *  - registration.register_player → register / update a player
 */

class RegistrationPanel extends window.McPanel.Base {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._roster = [];
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
        .form-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; }
        .form-row input, .form-row select {
          flex: 1; min-width: 120px; padding: 8px; border-radius: 6px;
          background: var(--input-background, #1e2a45); border: 1px solid var(--divider-color, #2a3555);
          color: var(--primary-text-color); font-size: 0.9rem;
        }
        .btn { padding: 8px 18px; border-radius: 6px; border: none; cursor: pointer; font-size: 0.9rem; }
        .btn-primary { background: var(--primary-color, #3d85c8); color: #fff; }
        .btn-secondary { background: var(--secondary-background-color, #1e2a45); color: var(--primary-text-color); }
        .count-badge { font-size: 0.85rem; color: var(--secondary-text-color); margin-left: 8px; }
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
            <div class="card-header">Register / Update Player</div>
            <div class="card-body">
              <div class="form-row">
                <input id="f-name"    type="text"   placeholder="Name" />
                <input id="f-role"    type="text"   placeholder="Role (e.g. hunter)" />
                <select id="f-neocorp">
                  <option value="">NeoCorp…</option>
                  <option value="Freelancer">Freelancer</option>
                  <option value="Helix">Helix</option>
                  <option value="Endline">Endline</option>
                  <option value="Reboot">Reboot</option>
                </select>
                <input id="f-faction" type="text"   placeholder="Faction" />
                <button class="btn btn-primary" id="register-btn">Register</button>
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
      .getElementById("register-btn")
      .addEventListener("click", () => this._registerPlayer());

    await this._loadRoster();
  }

  // -------------------------------------------------------------------------
  // Data
  // -------------------------------------------------------------------------

  _formatErr(err) {
    if (err == null) return "unknown error";
    if (typeof err === "string") return err;
    return err.message || err.error || err.code || JSON.stringify(err);
  }

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
            <th>ID</th><th>Name</th><th>Role</th><th>NeoCorp</th><th>Faction</th>
          </tr>
        </thead>
        <tbody>
          ${this._roster
            .map(
              (p) => `
            <tr>
              <td>${this._esc(p.id ?? "")}</td>
              <td>${this._esc(p.name ?? "")}</td>
              <td>${this._esc(p.role ?? "")}</td>
              <td>${this._esc(p.neocorp ?? "")}</td>
              <td>${this._esc(p.faction ?? "")}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  // -------------------------------------------------------------------------
  // Actions — all through HA services / websocket, zero direct LAN fetch
  // -------------------------------------------------------------------------

  async _syncNow() {
    try {
      await this._hass.callService("registration", "sync_now", {});
      this._feedback("Syncing…", "ok");
      // Give the coordinator a moment then reload the panel roster.
      setTimeout(() => this._loadRoster(), 1500);
    } catch (err) {
      this._feedback("Sync failed: " + this._formatErr(err), "err");
    }
  }

  async _registerPlayer() {
    const name = this.shadowRoot.getElementById("f-name").value.trim();
    if (!name) {
      this._feedback("Name is required.", "warn");
      return;
    }
    const payload = {
      name,
      role: this.shadowRoot.getElementById("f-role").value.trim(),
      neocorp: this.shadowRoot.getElementById("f-neocorp").value,
      faction: this.shadowRoot.getElementById("f-faction").value.trim(),
    };
    try {
      await this._hass.callService("registration", "register_player", payload);
      this._feedback("Player registered.", "ok");
      // Clear the form.
      ["f-name", "f-role", "f-faction"].forEach(
        (id) => (this.shadowRoot.getElementById(id).value = "")
      );
      this.shadowRoot.getElementById("f-neocorp").value = "";
      await this._loadRoster();
    } catch (err) {
      this._feedback("Registration failed: " + this._formatErr(err), "err");
    }
  }
}

customElements.define("registration-panel", RegistrationPanel);
