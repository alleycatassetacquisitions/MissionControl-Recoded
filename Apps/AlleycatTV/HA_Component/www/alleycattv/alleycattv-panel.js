/**
 * AlleycatTV live control panel — play/stop/interrupt over HA services.
 *
 * Extends McPanelBase. Reads devices via alleycattv/get_devices.
 * Writes only via hass.callService — no LAN fetch.
 */
class AlleycatTVPanel extends window.McPanel.Base {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._devices = [];
    this._areas = [];
    this._selected = "";
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
        .field input, .field select {
          width: 100%; padding: 8px; border-radius: 6px; box-sizing: border-box;
          background: var(--input-background, #1e2a45); border: 1px solid var(--divider-color, #2a3555);
          color: var(--primary-text-color); font-size: 0.9rem;
        }
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
        .hint { color: var(--secondary-text-color); font-size: 0.85rem; }
        .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
      </style>
      <div class="wrap">
        <header class="page-header">
          <h1>AlleycatTV</h1>
          <div class="header-actions">
            <span id="feedback" class="feedback"></span>
            <button class="btn btn-secondary" id="refresh-btn">Refresh</button>
          </div>
        </header>

        <div class="card" style="margin-bottom:16px">
          <div class="card-header">TV endpoints</div>
          <div class="card-body">
            <div class="chip-row" id="device-chips">
              <span class="hint">No devices yet — waiting for mc/tv/status/…</span>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">Playback</div>
          <div class="card-body">
            <div class="form-grid">
              <div class="field">
                <label for="bg-id">Broadcast Group ID</label>
                <input id="bg-id" placeholder="e.g. lobby" />
              </div>
              <div class="field">
                <label for="volume">Volume %</label>
                <input id="volume" type="number" min="0" max="100" value="80" />
              </div>
              <div class="field wide">
                <label for="file-url">Interrupt file URL</label>
                <input id="file-url" placeholder="http://…/media/announcements/alert.mp4" />
              </div>
              <div class="field">
                <label for="area-id">Area (placement)</label>
                <select id="area-id"><option value="">—</option></select>
              </div>
            </div>
            <div class="actions">
              <button class="btn btn-primary" id="btn-play">Play group</button>
              <button class="btn btn-secondary" id="btn-stop">Stop group</button>
              <button class="btn btn-secondary" id="btn-reload">Reload playlist</button>
              <button class="btn btn-secondary" id="btn-volume">Set volume</button>
              <button class="btn btn-secondary" id="btn-interrupt-bg">Interrupt group</button>
              <button class="btn btn-secondary" id="btn-interrupt-pi">Interrupt selected Pi</button>
              <button class="btn btn-secondary" id="btn-place">Set placement</button>
            </div>
            <p class="hint">Commands publish via Home Assistant MQTT only. Membership is Phase 7.</p>
          </div>
        </div>
      </div>
    `;
    this._wire();
  }

  _wire() {
    const root = this.shadowRoot;
    root.getElementById("refresh-btn").onclick = () => this._boot();
    root.getElementById("btn-play").onclick = () => this._callBg("play_broadcast_group");
    root.getElementById("btn-stop").onclick = () => this._callBg("stop_broadcast_group");
    root.getElementById("btn-reload").onclick = () => this._callBg("reload_playlist");
    root.getElementById("btn-volume").onclick = async () => {
      const bg = root.getElementById("bg-id").value.trim();
      if (!bg) return this._feedback("Broadcast Group ID required", "err");
      const volume = Number(root.getElementById("volume").value);
      await this.hass.callService("alleycattv", "set_volume_broadcast_group", {
        broadcast_group_id: bg,
        volume,
      });
      this._feedback("Volume set", "ok");
    };
    root.getElementById("btn-interrupt-bg").onclick = async () => {
      const bg = root.getElementById("bg-id").value.trim();
      const file_url = root.getElementById("file-url").value.trim();
      if (!bg || !file_url) return this._feedback("Group + file URL required", "err");
      await this.hass.callService("alleycattv", "interrupt_broadcast_group", {
        broadcast_group_id: bg,
        file_url,
      });
      this._feedback("Interrupt sent", "ok");
    };
    root.getElementById("btn-interrupt-pi").onclick = async () => {
      const file_url = root.getElementById("file-url").value.trim();
      if (!this._selected || !file_url) return this._feedback("Select a Pi + file URL", "err");
      await this.hass.callService("alleycattv", "interrupt_pi", {
        pi_id: this._selected,
        file_url,
      });
      this._feedback("Pi interrupt sent", "ok");
    };
    root.getElementById("btn-place").onclick = async () => {
      if (!this._selected) return this._feedback("Select a Pi", "err");
      const area_id = root.getElementById("area-id").value;
      await this.hass.callWS({
        type: "alleycattv/set_placement",
        pi_id: this._selected,
        area_id: area_id || "",
      });
      this._feedback("Placement saved", "ok");
      await this._boot();
    };
  }

  async _callBg(service) {
    const bg = this.shadowRoot.getElementById("bg-id").value.trim();
    if (!bg) return this._feedback("Broadcast Group ID required", "err");
    await this.hass.callService("alleycattv", service, { broadcast_group_id: bg });
    this._feedback(`${service} sent`, "ok");
  }

  async _boot() {
    if (!this.hass) return;
    try {
      const [dev, areas] = await Promise.all([
        this.hass.callWS({ type: "alleycattv/get_devices" }),
        this.hass.callWS({ type: "alleycattv/list_areas" }),
      ]);
      this._devices = (dev && dev.devices) || [];
      this._areas = (areas && areas.areas) || [];
      this._paint();
    } catch (err) {
      this._feedback(String(err), "err");
    }
  }

  _paint() {
    const chips = this.shadowRoot.getElementById("device-chips");
    if (!this._devices.length) {
      chips.innerHTML = `<span class="hint">No devices yet — waiting for mc/tv/status/…</span>`;
    } else {
      chips.innerHTML = this._devices
        .map((d) => {
          const id = this._esc(d.device_id || "");
          const presence = (d.presence || "unknown").toLowerCase();
          const sel = id === this._selected ? "selected" : "";
          return `<button class="chip ${sel}" data-id="${id}">
            <span class="dot ${presence}"></span>${id}
            ${d.broadcast_group_id ? ` · ${this._esc(d.broadcast_group_id)}` : ""}
          </button>`;
        })
        .join("");
      chips.querySelectorAll(".chip").forEach((el) => {
        el.onclick = () => {
          this._selected = el.getAttribute("data-id") || "";
          const d = this._devices.find((x) => x.device_id === this._selected);
          if (d && d.broadcast_group_id) {
            this.shadowRoot.getElementById("bg-id").value = d.broadcast_group_id;
          }
          this._paint();
        };
      });
    }
    const areaSel = this.shadowRoot.getElementById("area-id");
    const cur = this._devices.find((d) => d.device_id === this._selected);
    areaSel.innerHTML =
      `<option value="">—</option>` +
      this._areas
        .map(
          (a) =>
            `<option value="${this._esc(a.area_id)}" ${
              cur && cur.area_id === a.area_id ? "selected" : ""
            }>${this._esc(a.name)}</option>`
        )
        .join("");
  }

  connectedCallback() {
    this._render();
    this._boot();
  }
}

customElements.define("alleycattv-panel", AlleycatTVPanel);
