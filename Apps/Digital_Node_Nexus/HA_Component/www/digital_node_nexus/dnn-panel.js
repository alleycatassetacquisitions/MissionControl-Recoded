/**
 * Digital Node Nexus panel — paging-first operator UI for FDNs.
 *
 * Design contract:
 *  - Extends McPanelBase from shared_libraries/mc-panel.js.
 *  - ALL reads/writes go through hass.callWS / hass.callService.
 *    Zero direct fetch() to MCS or any LAN IP.
 *
 * Websocket:
 *  - digital_node_nexus/get_devices → fabric presence list
 *  - digital_node_nexus/get_roster → MCS players (read-only)
 *
 * HA services:
 *  - digital_node_nexus.page
 *  - digital_node_nexus.set_led
 *  - digital_node_nexus.trigger_haptic
 */

class DnnPanel extends window.McPanel.Base {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._devices = [];
    this._players = [];
    this._tab = "page";
    this._selectedDevice = "";
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
        .tabs { display: flex; gap: 8px; margin: 12px 0 16px; flex-wrap: wrap; }
        .tab {
          padding: 8px 14px; border-radius: 6px; border: 1px solid var(--divider-color, #2a3555);
          background: transparent; color: var(--primary-text-color); cursor: pointer;
        }
        .tab.active { background: var(--primary-color, #3d85c8); color: #fff; border-color: transparent; }
        .form-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
          gap: 12px 16px;
          align-items: end;
        }
        .field { display: flex; flex-direction: column; gap: 4px; }
        .field.wide { grid-column: 1 / -1; }
        .field label {
          font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em;
          color: var(--secondary-text-color);
        }
        .field input, .field select, .field textarea {
          width: 100%; padding: 8px; border-radius: 6px; box-sizing: border-box;
          background: var(--input-background, #1e2a45); border: 1px solid var(--divider-color, #2a3555);
          color: var(--primary-text-color); font-size: 0.9rem;
        }
        .field textarea { min-height: 72px; resize: vertical; }
        .btn { padding: 8px 18px; border-radius: 6px; border: none; cursor: pointer; font-size: 0.9rem; }
        .btn-primary { background: var(--primary-color, #3d85c8); color: #fff; }
        .btn-secondary { background: var(--secondary-background-color, #1e2a45); color: var(--primary-text-color); }
        .chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
        .chip {
          padding: 6px 10px; border-radius: 6px; border: 1px solid var(--divider-color, #2a3555);
          background: transparent; color: var(--primary-text-color); cursor: pointer; font-size: 0.85rem;
        }
        .chip.selected { border-color: var(--primary-color, #3d85c8); color: var(--primary-color, #3d85c8); }
        .chip .dot {
          display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px;
          background: var(--disabled-text-color, #888);
        }
        .chip .dot.online { background: var(--success-color, #4caf50); }
        .chip .dot.offline { background: var(--error-color, #f44336); }
        .hint { color: var(--secondary-text-color); font-size: 0.85rem; margin-top: 8px; }
        .hidden { display: none !important; }
      </style>

      <div class="wrap">
        <header class="page-header">
          <h1>Digital Node Nexus</h1>
          <div class="header-actions">
            <span id="feedback" class="feedback"></span>
            <button class="btn btn-secondary" id="refresh-btn">Refresh</button>
          </div>
        </header>

        <div class="tabs">
          <button class="tab active" data-tab="page" id="tab-page">Page</button>
          <button class="tab" data-tab="led" id="tab-led">LED</button>
          <button class="tab" data-tab="haptic" id="tab-haptic">Haptic</button>
        </div>

        <div class="card" style="margin-bottom:16px">
          <div class="card-header">FDNs</div>
          <div class="card-body">
            <div class="chip-row" id="device-chips">
              <span class="hint">No devices yet — waiting for mc/dnn/status/…</span>
            </div>
          </div>
        </div>

        <div id="panel-page" class="card">
          <div class="card-header">Page</div>
          <div class="card-body">
            <div class="form-grid">
              <div class="field wide">
                <label for="page-message">Message</label>
                <textarea id="page-message" placeholder="Message to page…"></textarea>
              </div>
              <div class="field">
                <label for="page-target-mode">Target</label>
                <select id="page-target-mode">
                  <option value="device">Selected FDN</option>
                  <option value="all">All FDNs</option>
                  <option value="broadcast">Broadcast Group</option>
                  <option value="player">Player</option>
                  <option value="filter">Role / NeoCorp filter</option>
                </select>
              </div>
              <div class="field" id="page-broadcast-wrap">
                <label for="page-broadcast">Broadcast Group ID</label>
                <input id="page-broadcast" type="text" autocomplete="off" />
              </div>
              <div class="field" id="page-player-wrap">
                <label for="page-player">Player</label>
                <select id="page-player"></select>
              </div>
              <div class="field" id="page-role-wrap">
                <label for="page-role">Role</label>
                <select id="page-role">
                  <option value="">(any)</option>
                  <option value="hunter">Hunter</option>
                  <option value="bounty">Bounty</option>
                </select>
              </div>
              <div class="field" id="page-neocorp-wrap">
                <label for="page-neocorp">NeoCorp</label>
                <select id="page-neocorp">
                  <option value="">(any)</option>
                  <option value="freelancer">Freelancer</option>
                  <option value="helix">Helix</option>
                  <option value="endline">Endline</option>
                  <option value="reboot">Reboot</option>
                </select>
              </div>
              <div class="field">
                <label for="page-duration">Duration (s)</label>
                <input id="page-duration" type="number" min="1" max="60" value="10" />
              </div>
              <div class="field">
                <label for="page-scroll">Scroll</label>
                <select id="page-scroll">
                  <option value="false">No</option>
                  <option value="true">Yes</option>
                </select>
              </div>
              <div class="field">
                <button class="btn btn-primary" id="page-send">Send Page</button>
              </div>
            </div>
            <p class="hint">Paging starts a state machine on the FDN. Player / filter stamps travel in the payload; until placement exists they route on cmd/all. Broker: official Mosquitto add-on via HA mqtt.</p>
          </div>
        </div>

        <div id="panel-led" class="card hidden">
          <div class="card-header">LED</div>
          <div class="card-body">
            <div class="form-grid">
              <div class="field">
                <label for="led-target">Target</label>
                <select id="led-target">
                  <option value="device">Selected FDN</option>
                  <option value="all">All FDNs</option>
                </select>
              </div>
              <div class="field">
                <label for="led-state">State</label>
                <select id="led-state">
                  <option value="true">On</option>
                  <option value="false">Off</option>
                </select>
              </div>
              <div class="field">
                <label for="led-effect">Effect</label>
                <select id="led-effect">
                  <option value="solid">Solid</option>
                  <option value="blink">Blink</option>
                  <option value="pulse">Pulse</option>
                  <option value="rainbow">Rainbow</option>
                </select>
              </div>
              <div class="field">
                <label for="led-brightness">Brightness</label>
                <input id="led-brightness" type="number" min="0" max="255" value="255" />
              </div>
              <div class="field">
                <label for="led-r">R</label>
                <input id="led-r" type="number" min="0" max="255" value="255" />
              </div>
              <div class="field">
                <label for="led-g">G</label>
                <input id="led-g" type="number" min="0" max="255" value="0" />
              </div>
              <div class="field">
                <label for="led-b">B</label>
                <input id="led-b" type="number" min="0" max="255" value="0" />
              </div>
              <div class="field">
                <button class="btn btn-primary" id="led-send">Set LED</button>
              </div>
            </div>
          </div>
        </div>

        <div id="panel-haptic" class="card hidden">
          <div class="card-header">Haptic</div>
          <div class="card-body">
            <div class="form-grid">
              <div class="field">
                <label for="haptic-target">Target</label>
                <select id="haptic-target">
                  <option value="device">Selected FDN</option>
                  <option value="all">All FDNs</option>
                </select>
              </div>
              <div class="field">
                <label for="haptic-pattern">Pattern</label>
                <select id="haptic-pattern">
                  <option value="short">Short</option>
                  <option value="long">Long</option>
                  <option value="double">Double</option>
                  <option value="sos">SOS</option>
                  <option value="custom">Custom</option>
                </select>
              </div>
              <div class="field">
                <label for="haptic-intensity">Intensity</label>
                <input id="haptic-intensity" type="number" min="0" max="255" value="255" />
              </div>
              <div class="field">
                <label for="haptic-duration">Duration (ms)</label>
                <input id="haptic-duration" type="number" min="1" max="5000" value="100" />
              </div>
              <div class="field">
                <label for="haptic-repeat">Repeat</label>
                <input id="haptic-repeat" type="number" min="1" max="20" value="1" />
              </div>
              <div class="field">
                <button class="btn btn-primary" id="haptic-send">Trigger Haptic</button>
              </div>
            </div>
          </div>
        </div>
      </div>`;
  }

  async _boot() {
    this.shadowRoot.getElementById("refresh-btn").addEventListener("click", () => this._refresh());
    this.shadowRoot.getElementById("page-send").addEventListener("click", () => this._sendPage());
    this.shadowRoot.getElementById("led-send").addEventListener("click", () => this._sendLed());
    this.shadowRoot.getElementById("haptic-send").addEventListener("click", () => this._sendHaptic());
    this.shadowRoot.getElementById("page-target-mode").addEventListener("change", () => this._syncPageTargetFields());

    for (const tab of this.shadowRoot.querySelectorAll(".tab")) {
      tab.addEventListener("click", () => this._setTab(tab.dataset.tab));
    }

    this._syncPageTargetFields();
    await this._refresh();
  }

  _formatErr(err) {
    if (err == null) return "unknown error";
    if (typeof err === "string") return err;
    return err.message || String(err);
  }

  _setTab(tab) {
    this._tab = tab;
    for (const el of this.shadowRoot.querySelectorAll(".tab")) {
      el.classList.toggle("active", el.dataset.tab === tab);
    }
    this.shadowRoot.getElementById("panel-page").classList.toggle("hidden", tab !== "page");
    this.shadowRoot.getElementById("panel-led").classList.toggle("hidden", tab !== "led");
    this.shadowRoot.getElementById("panel-haptic").classList.toggle("hidden", tab !== "haptic");
  }

  _syncPageTargetFields() {
    const mode = this.shadowRoot.getElementById("page-target-mode").value;
    this.shadowRoot.getElementById("page-broadcast-wrap").classList.toggle("hidden", mode !== "broadcast");
    this.shadowRoot.getElementById("page-player-wrap").classList.toggle("hidden", mode !== "player");
    const filter = mode === "filter";
    this.shadowRoot.getElementById("page-role-wrap").classList.toggle("hidden", !filter);
    this.shadowRoot.getElementById("page-neocorp-wrap").classList.toggle("hidden", !filter);
  }

  async _refresh() {
    await Promise.all([this._loadDevices(), this._loadRoster()]);
  }

  async _loadDevices() {
    try {
      const result = await this._hass.callWS({ type: "digital_node_nexus/get_devices" });
      this._devices = (result && result.devices) || [];
      this._renderDevices();
    } catch (err) {
      this._feedback("Devices: " + this._formatErr(err), "err");
    }
  }

  async _loadRoster() {
    try {
      const result = await this._hass.callWS({ type: "digital_node_nexus/get_roster" });
      this._players = (result && result.players) || [];
      this._renderPlayers();
    } catch (err) {
      this._feedback("Roster: " + this._formatErr(err), "err");
    }
  }

  _renderDevices() {
    const host = this.shadowRoot.getElementById("device-chips");
    if (!this._devices.length) {
      host.innerHTML = `<span class="hint">No devices yet — waiting for mc/dnn/status/…</span>`;
      return;
    }
    host.innerHTML = this._devices
      .map((d) => {
        const id = this._esc(d.device_id);
        const presence = this._esc(d.presence || "unknown");
        const selected = d.device_id === this._selectedDevice ? " selected" : "";
        return `<button type="button" class="chip${selected}" data-device="${id}">
          <span class="dot ${presence}"></span>${id} (${presence})
        </button>`;
      })
      .join("");
    for (const chip of host.querySelectorAll(".chip")) {
      chip.addEventListener("click", () => {
        this._selectedDevice = chip.dataset.device;
        this._renderDevices();
      });
    }
  }

  _renderPlayers() {
    const select = this.shadowRoot.getElementById("page-player");
    const previous = select.value;
    const options = ['<option value="">Select player…</option>'].concat(
      this._players.map((p) => {
        const id = this._esc(p.id || "");
        const name = this._esc(p.name || id);
        const role = this._esc(p.role || "");
        const neocorp = this._esc(p.neocorp || "");
        return `<option value="${id}">${name} (${role}/${neocorp})</option>`;
      })
    );
    select.innerHTML = options.join("");
    if (previous) select.value = previous;
  }

  _requireDeviceOrAll(modeSelectId) {
    const mode = this.shadowRoot.getElementById(modeSelectId).value;
    if (mode === "all") return { target: "all" };
    if (!this._selectedDevice) {
      this._feedback("Select an FDN chip first", "warn");
      return null;
    }
    return { device_id: this._selectedDevice };
  }

  async _sendPage() {
    const message = this.shadowRoot.getElementById("page-message").value.trim();
    if (!message) {
      this._feedback("Message is required", "warn");
      return;
    }
    const mode = this.shadowRoot.getElementById("page-target-mode").value;
    const payload = {
      message,
      duration: Number(this.shadowRoot.getElementById("page-duration").value || 10),
      scroll: this.shadowRoot.getElementById("page-scroll").value === "true",
    };

    if (mode === "device") {
      if (!this._selectedDevice) {
        this._feedback("Select an FDN chip first", "warn");
        return;
      }
      payload.device_id = this._selectedDevice;
    } else if (mode === "all") {
      payload.target = "all";
    } else if (mode === "broadcast") {
      const bg = this.shadowRoot.getElementById("page-broadcast").value.trim();
      if (!bg) {
        this._feedback("Broadcast Group ID is required", "warn");
        return;
      }
      payload.broadcast_group_id = bg;
    } else if (mode === "player") {
      const playerId = this.shadowRoot.getElementById("page-player").value;
      if (!playerId) {
        this._feedback("Select a player", "warn");
        return;
      }
      payload.player_id = playerId;
    } else if (mode === "filter") {
      const role = this.shadowRoot.getElementById("page-role").value;
      const neocorp = this.shadowRoot.getElementById("page-neocorp").value;
      if (!role && !neocorp) {
        this._feedback("Pick a role and/or NeoCorp", "warn");
        return;
      }
      if (role) payload.role = role;
      if (neocorp) payload.neocorp = neocorp;
    }

    try {
      await this._hass.callService("digital_node_nexus", "page", payload);
      this._feedback("Page sent", "ok");
    } catch (err) {
      this._feedback("Page failed: " + this._formatErr(err), "err");
    }
  }

  async _sendLed() {
    const target = this._requireDeviceOrAll("led-target");
    if (!target) return;
    const payload = {
      ...target,
      state: this.shadowRoot.getElementById("led-state").value === "true",
      effect: this.shadowRoot.getElementById("led-effect").value,
      brightness: Number(this.shadowRoot.getElementById("led-brightness").value || 255),
      r: Number(this.shadowRoot.getElementById("led-r").value || 0),
      g: Number(this.shadowRoot.getElementById("led-g").value || 0),
      b: Number(this.shadowRoot.getElementById("led-b").value || 0),
    };
    try {
      await this._hass.callService("digital_node_nexus", "set_led", payload);
      this._feedback("LED command sent", "ok");
    } catch (err) {
      this._feedback("LED failed: " + this._formatErr(err), "err");
    }
  }

  async _sendHaptic() {
    const target = this._requireDeviceOrAll("haptic-target");
    if (!target) return;
    const payload = {
      ...target,
      pattern: this.shadowRoot.getElementById("haptic-pattern").value,
      intensity: Number(this.shadowRoot.getElementById("haptic-intensity").value || 255),
      duration_ms: Number(this.shadowRoot.getElementById("haptic-duration").value || 100),
      repeat: Number(this.shadowRoot.getElementById("haptic-repeat").value || 1),
    };
    try {
      await this._hass.callService("digital_node_nexus", "trigger_haptic", payload);
      this._feedback("Haptic command sent", "ok");
    } catch (err) {
      this._feedback("Haptic failed: " + this._formatErr(err), "err");
    }
  }
}

customElements.define("dnn-panel", DnnPanel);
