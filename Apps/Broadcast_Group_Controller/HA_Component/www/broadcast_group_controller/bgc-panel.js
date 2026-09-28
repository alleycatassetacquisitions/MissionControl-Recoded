/**
 * Broadcast Group Controller panel — Area placement + Broadcast Group membership.
 *
 * Extends McPanelBase. Reads via websocket; writes via hass.callService only.
 */
class BroadcastGroupControllerPanel extends window.McPanel.Base {
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

  _formatErr(err) {
    if (err == null) return "unknown error";
    if (typeof err === "string") return err;
    if (err.message) return err.message;
    if (err.error) return err.error;
    try {
      return JSON.stringify(err);
    } catch (_) {
      return String(err);
    }
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
          <h1>Broadcast Groups</h1>
          <div class="header-actions">
            <span id="feedback" class="feedback"></span>
            <button class="btn btn-secondary" id="refresh-btn">Refresh</button>
          </div>
        </header>
        <p class="hint">
          Physical placement is a Home Assistant Area. Command membership is a Broadcast Group.
          AlleycatTV Content owns playlist buckets; this panel assigns devices to those ids.
        </p>
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">Fabric devices</div>
          <div class="card-body">
            <div class="chip-row" id="device-chips">
              <span class="hint">No devices yet — waiting for fabric presence.</span>
            </div>
          </div>
        </div>
        <div class="card">
          <div class="card-header">Placement &amp; membership</div>
          <div class="card-body">
            <div class="form-grid">
              <div class="field">
                <label for="area-id">Area (placement)</label>
                <select id="area-id"><option value="">—</option></select>
              </div>
              <div class="field">
                <label for="bg-id">Broadcast Group ID</label>
                <input id="bg-id" placeholder="e.g. lobby" />
              </div>
            </div>
            <div class="actions">
              <button class="btn btn-primary" id="btn-area">Set area</button>
              <button class="btn btn-primary" id="btn-bg">Set broadcast group</button>
              <button class="btn btn-secondary" id="btn-clear">Clear broadcast group</button>
            </div>
          </div>
        </div>
      </div>
    `;
    this._wire();
  }

  _wire() {
    const root = this.shadowRoot;
    root.getElementById("refresh-btn").onclick = () => this._boot();
    root.getElementById("btn-area").onclick = async () => {
      try {
        const sel = this._selectedDevice();
        if (!sel) return this._feedback("Select a device", "err");
        const area_id = root.getElementById("area-id").value;
        await this.hass.callService("broadcast_group_controller", "set_area", {
          kind: sel.kind,
          device_id: sel.device_id,
          area_id,
        });
        this._feedback("Area set", "ok");
        await this._boot();
      } catch (err) {
        this._feedback(this._formatErr(err), "err");
      }
    };
    root.getElementById("btn-bg").onclick = async () => {
      try {
        const sel = this._selectedDevice();
        if (!sel) return this._feedback("Select a device", "err");
        const broadcast_group_id = root.getElementById("bg-id").value.trim();
        await this.hass.callService(
          "broadcast_group_controller",
          "set_broadcast_group",
          { kind: sel.kind, device_id: sel.device_id, broadcast_group_id }
        );
        this._feedback("Broadcast Group assigned", "ok");
        await this._boot();
      } catch (err) {
        this._feedback(this._formatErr(err), "err");
      }
    };
    root.getElementById("btn-clear").onclick = async () => {
      try {
        const sel = this._selectedDevice();
        if (!sel) return this._feedback("Select a device", "err");
        await this.hass.callService(
          "broadcast_group_controller",
          "clear_broadcast_group",
          { kind: sel.kind, device_id: sel.device_id }
        );
        root.getElementById("bg-id").value = "";
        this._feedback("Broadcast Group cleared", "ok");
        await this._boot();
      } catch (err) {
        this._feedback(this._formatErr(err), "err");
      }
    };
  }

  _selectedDevice() {
    if (!this._selected) return null;
    const [kind, ...rest] = this._selected.split(":");
    return { kind, device_id: rest.join(":") };
  }

  async _boot() {
    if (!this.hass) return;
    try {
      const [devRes, areaRes] = await Promise.all([
        this.hass.callWS({ type: "broadcast_group_controller/list_devices" }),
        this.hass.callWS({ type: "broadcast_group_controller/list_areas" }),
      ]);
      this._devices = Array.isArray(devRes?.devices) ? devRes.devices : [];
      this._areas = Array.isArray(areaRes?.areas) ? areaRes.areas : [];
      this._paint();
      this._feedback("Refreshed", "ok");
    } catch (err) {
      const msg = this._formatErr(err);
      if (/unknown_command|not found/i.test(msg)) {
        this._feedback(
          "Add Broadcast Group Controller integration (Settings → Devices & services)",
          "err"
        );
      } else {
        this._feedback(msg, "err");
      }
    }
  }

  _paint() {
    const root = this.shadowRoot;
    const areaSel = root.getElementById("area-id");
    const prevArea = areaSel.value;
    areaSel.innerHTML =
      `<option value="">—</option>` +
      this._areas
        .map(
          (a) =>
            `<option value="${this._esc(a.area_id)}">${this._esc(a.name || a.area_id)}</option>`
        )
        .join("");
    if (prevArea) areaSel.value = prevArea;

    const chips = root.getElementById("device-chips");
    if (!this._devices.length) {
      chips.innerHTML = `<span class="hint">No devices yet — waiting for fabric presence.</span>`;
      return;
    }
    chips.innerHTML = this._devices
      .map((d) => {
        const key = `${d.kind}:${d.device_id}`;
        const online = d.presence === "online";
        const sel = key === this._selected ? " selected" : "";
        const bg = d.broadcast_group_id
          ? ` · ${this._esc(d.broadcast_group_id)}`
          : "";
        return `<button type="button" class="chip${sel}" data-key="${this._esc(key)}">
          <span class="dot ${online ? "online" : "offline"}"></span>${this._esc(d.kind)}/${this._esc(d.device_id)}${bg}
        </button>`;
      })
      .join("");
    chips.querySelectorAll(".chip").forEach((btn) => {
      btn.onclick = () => {
        this._selected = btn.dataset.key;
        const d = this._devices.find(
          (x) => `${x.kind}:${x.device_id}` === this._selected
        );
        if (d) {
          root.getElementById("bg-id").value = d.broadcast_group_id || "";
          root.getElementById("area-id").value = d.area_id || "";
        }
        this._paint();
      };
    });
  }

  connectedCallback() {
    if (!this.shadowRoot.innerHTML) this._render();
    this._boot();
  }
}

customElements.define("broadcast-group-controller-panel", BroadcastGroupControllerPanel);
