"use strict";
(() => {
  // src/panels/bgc-panel.ts
  var BroadcastGroupControllerPanel = class extends window.McPanel.Base {
    static get properties() {
      return {
        ...super.properties,
        _devices: { state: true },
        _areas: { state: true },
        _selected: { state: true },
        _areaId: { state: true },
        _bgId: { state: true }
      };
    }
    constructor() {
      super();
      this._devices = [];
      this._areas = [];
      this._selected = "";
      this._areaId = "";
      this._bgId = "";
    }
    static get styles() {
      const base = super.styles;
      const baseArr = Array.isArray(base) ? base : base ? [base] : [];
      return [
        ...baseArr,
        window.McPanel.css`
        .form-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
          gap: 12px 16px;
          align-items: end;
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
        .chip-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 8px;
        }
        .chip {
          padding: 6px 10px;
          border-radius: 6px;
          border: 1px solid var(--divider-color, #2a3555);
          background: transparent;
          color: var(--primary-text-color);
          cursor: pointer;
          font-size: 0.85rem;
        }
        .chip.selected {
          border-color: var(--primary-color, #3d85c8);
          color: var(--primary-color, #3d85c8);
        }
        .chip .dot {
          display: inline-block;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          margin-right: 6px;
          background: var(--disabled-text-color, #888);
        }
        .chip .dot.online {
          background: var(--success-color, #4caf50);
        }
        .chip .dot.offline {
          background: var(--error-color, #f44336);
        }
        .actions {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-top: 12px;
        }
      `
      ];
    }
    _formatErr(err) {
      if (err == null) return "unknown error";
      if (typeof err === "string") return err;
      const e = err;
      if (e.message) return e.message;
      if (e.error) return e.error;
      try {
        return JSON.stringify(err);
      } catch (_) {
        return String(err);
      }
    }
    _selectedDevice() {
      if (!this._selected) return null;
      const [kind, ...rest] = this._selected.split(":");
      return { kind, device_id: rest.join(":") };
    }
    _selectDevice(key) {
      this._selected = key;
      const d = this._devices.find((x) => `${x.kind}:${x.device_id}` === key);
      if (d) {
        this._bgId = d.broadcast_group_id || "";
        this._areaId = d.area_id || "";
      }
    }
    async _boot() {
      if (!this.hass) return;
      try {
        const [devRes, areaRes] = await Promise.all([
          this.hass.callWS({
            type: "broadcast_group_controller/list_devices"
          }),
          this.hass.callWS({
            type: "broadcast_group_controller/list_areas"
          })
        ]);
        this._devices = Array.isArray(devRes?.devices) ? devRes.devices : [];
        this._areas = Array.isArray(areaRes?.areas) ? areaRes.areas : [];
        this._feedback("Refreshed", "ok");
      } catch (err) {
        const msg = this._formatErr(err);
        if (/unknown_command|not found/i.test(msg)) {
          this._feedback(
            "Add Broadcast Group Controller integration (Settings \u2192 Devices & services)",
            "err"
          );
        } else {
          this._feedback(msg, "err");
        }
      }
    }
    async _setArea() {
      try {
        const sel = this._selectedDevice();
        if (!sel) return this._feedback("Select a device", "err");
        await this.hass.callService("broadcast_group_controller", "set_area", {
          kind: sel.kind,
          device_id: sel.device_id,
          area_id: this._areaId
        });
        this._feedback("Area set", "ok");
        await this._boot();
      } catch (err) {
        this._feedback(this._formatErr(err), "err");
      }
    }
    async _setBg() {
      try {
        const sel = this._selectedDevice();
        if (!sel) return this._feedback("Select a device", "err");
        await this.hass.callService(
          "broadcast_group_controller",
          "set_broadcast_group",
          {
            kind: sel.kind,
            device_id: sel.device_id,
            broadcast_group_id: this._bgId.trim()
          }
        );
        this._feedback("Broadcast Group assigned", "ok");
        await this._boot();
      } catch (err) {
        this._feedback(this._formatErr(err), "err");
      }
    }
    async _clearBg() {
      try {
        const sel = this._selectedDevice();
        if (!sel) return this._feedback("Select a device", "err");
        await this.hass.callService(
          "broadcast_group_controller",
          "clear_broadcast_group",
          { kind: sel.kind, device_id: sel.device_id }
        );
        this._bgId = "";
        this._feedback("Broadcast Group cleared", "ok");
        await this._boot();
      } catch (err) {
        this._feedback(this._formatErr(err), "err");
      }
    }
    render() {
      const html = window.McPanel.html;
      return html`
      <div class="wrap">
        <header class="page-header">
          <h1>Broadcast Groups</h1>
          <div class="header-actions">
            ${this._feedbackTemplate()}
            <button class="btn btn-secondary" @click=${() => this._boot()}>
              Refresh
            </button>
          </div>
        </header>
        <p class="hint">
          Physical placement is a Home Assistant Area. Command membership is a
          Broadcast Group. AlleycatTV Content owns playlist buckets; this panel
          assigns devices to those ids.
        </p>
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">Fabric devices</div>
          <div class="card-body">
            <div class="chip-row">
              ${this._devices.length ? this._devices.map((d) => {
        const key = `${d.kind}:${d.device_id}`;
        const online = d.presence === "online";
        const sel = key === this._selected ? " selected" : "";
        const bg = d.broadcast_group_id ? ` \xB7 ${d.broadcast_group_id}` : "";
        return html`<button
                      type="button"
                      class="chip${sel}"
                      @click=${() => this._selectDevice(key)}
                    >
                      <span
                        class="dot ${online ? "online" : "offline"}"
                      ></span
                      >${d.kind}/${d.device_id}${bg}
                    </button>`;
      }) : html`<span class="hint"
                    >No devices yet — waiting for fabric presence.</span
                  >`}
            </div>
          </div>
        </div>
        <div class="card">
          <div class="card-header">Placement &amp; membership</div>
          <div class="card-body">
            <div class="form-grid">
              <div class="field">
                <label for="area-id">Area (placement)</label>
                <select
                  id="area-id"
                  .value=${this._areaId}
                  @change=${(e) => {
        this._areaId = e.target.value;
      }}
                >
                  <option value="">—</option>
                  ${this._areas.map(
        (a) => html`<option value=${a.area_id}>
                        ${a.name || a.area_id}
                      </option>`
      )}
                </select>
              </div>
              <div class="field">
                <label for="bg-id">Broadcast Group ID</label>
                <input
                  id="bg-id"
                  placeholder="e.g. lobby"
                  .value=${this._bgId}
                  @input=${(e) => {
        this._bgId = e.target.value;
      }}
                />
              </div>
            </div>
            <div class="actions">
              <button class="btn btn-primary" @click=${() => this._setArea()}>
                Set area
              </button>
              <button class="btn btn-primary" @click=${() => this._setBg()}>
                Set broadcast group
              </button>
              <button
                class="btn btn-secondary"
                @click=${() => this._clearBg()}
              >
                Clear broadcast group
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
    }
  };
  customElements.define(
    "broadcast-group-controller-panel",
    BroadcastGroupControllerPanel
  );
})();
//# sourceMappingURL=bgc-panel.js.map
