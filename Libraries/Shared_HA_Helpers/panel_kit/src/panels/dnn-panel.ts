/// <reference path="../mc-panel/globals.d.ts" />
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

type DnnDevice = { device_id: string; presence?: string };
type DnnPlayer = {
  id?: string;
  name?: string;
  role?: string;
  neocorp?: string;
};

class DnnPanel extends window.McPanel.Base {
  static get properties() {
    return {
      ...super.properties,
      _devices: { state: true },
      _players: { state: true },
      _tab: { state: true },
      _selectedDevice: { state: true },
      _pageMessage: { state: true },
      _pageTargetMode: { state: true },
      _pageBroadcast: { state: true },
      _pagePlayer: { state: true },
      _pageRole: { state: true },
      _pageNeocorp: { state: true },
      _pageDuration: { state: true },
      _pageScroll: { state: true },
      _ledTarget: { state: true },
      _ledState: { state: true },
      _ledEffect: { state: true },
      _ledBrightness: { state: true },
      _ledR: { state: true },
      _ledG: { state: true },
      _ledB: { state: true },
      _hapticTarget: { state: true },
      _hapticPattern: { state: true },
      _hapticIntensity: { state: true },
      _hapticDuration: { state: true },
      _hapticRepeat: { state: true },
    };
  }

  declare _devices: DnnDevice[];
  declare _players: DnnPlayer[];
  declare _tab: string;
  declare _selectedDevice: string;
  declare _pageMessage: string;
  declare _pageTargetMode: string;
  declare _pageBroadcast: string;
  declare _pagePlayer: string;
  declare _pageRole: string;
  declare _pageNeocorp: string;
  declare _pageDuration: number;
  declare _pageScroll: string;
  declare _ledTarget: string;
  declare _ledState: string;
  declare _ledEffect: string;
  declare _ledBrightness: number;
  declare _ledR: number;
  declare _ledG: number;
  declare _ledB: number;
  declare _hapticTarget: string;
  declare _hapticPattern: string;
  declare _hapticIntensity: number;
  declare _hapticDuration: number;
  declare _hapticRepeat: number;

  constructor() {
    super();
    this._devices = [];
    this._players = [];
    this._tab = "page";
    this._selectedDevice = "";
    this._pageMessage = "";
    this._pageTargetMode = "device";
    this._pageBroadcast = "";
    this._pagePlayer = "";
    this._pageRole = "";
    this._pageNeocorp = "";
    this._pageDuration = 10;
    this._pageScroll = "false";
    this._ledTarget = "device";
    this._ledState = "true";
    this._ledEffect = "solid";
    this._ledBrightness = 255;
    this._ledR = 255;
    this._ledG = 0;
    this._ledB = 0;
    this._hapticTarget = "device";
    this._hapticPattern = "short";
    this._hapticIntensity = 255;
    this._hapticDuration = 100;
    this._hapticRepeat = 1;
  }

  static get styles() {
    const base = super.styles;
    const baseArr = Array.isArray(base) ? base : base ? [base] : [];
    return [
      ...baseArr,
      window.McPanel.css`
        .tabs {
          display: flex;
          gap: 8px;
          margin: 12px 0 16px;
          flex-wrap: wrap;
        }
        .tab {
          padding: 8px 14px;
          border-radius: 6px;
          border: 1px solid var(--divider-color, #2a3555);
          background: transparent;
          color: var(--primary-text-color);
          cursor: pointer;
        }
        .tab.active {
          background: var(--primary-color, #3d85c8);
          color: #fff;
          border-color: transparent;
        }
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
        .field.wide {
          grid-column: 1 / -1;
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
        .hidden {
          display: none !important;
        }
      `,
    ];
  }

  _formatErr(err: unknown): string {
    if (err == null) return "unknown error";
    if (typeof err === "string") return err;
    const e = err as { message?: string };
    return e.message || String(err);
  }

  override async _boot() {
    await this._refresh();
  }

  async _refresh() {
    await Promise.all([this._loadDevices(), this._loadRoster()]);
  }

  async _loadDevices() {
    try {
      const result = await this.hass!.callWS<{ devices?: DnnDevice[] }>({
        type: "digital_node_nexus/get_devices",
      });
      this._devices = (result && result.devices) || [];
    } catch (err) {
      this._feedback("Devices: " + this._formatErr(err), "err");
    }
  }

  async _loadRoster() {
    try {
      const result = await this.hass!.callWS<{ players?: DnnPlayer[] }>({
        type: "digital_node_nexus/get_roster",
      });
      this._players = (result && result.players) || [];
    } catch (err) {
      this._feedback("Roster: " + this._formatErr(err), "err");
    }
  }

  _requireDeviceOrAll(mode: string): Record<string, unknown> | null {
    if (mode === "all") return { target: "all" };
    if (!this._selectedDevice) {
      this._feedback("Select an FDN chip first", "warn");
      return null;
    }
    return { device_id: this._selectedDevice };
  }

  async _sendPage() {
    const message = this._pageMessage.trim();
    if (!message) {
      this._feedback("Message is required", "warn");
      return;
    }
    const mode = this._pageTargetMode;
    const payload: Record<string, unknown> = {
      message,
      duration: Number(this._pageDuration || 10),
      scroll: this._pageScroll === "true",
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
      const bg = this._pageBroadcast.trim();
      if (!bg) {
        this._feedback("Broadcast Group ID is required", "warn");
        return;
      }
      payload.broadcast_group_id = bg;
    } else if (mode === "player") {
      if (!this._pagePlayer) {
        this._feedback("Select a player", "warn");
        return;
      }
      payload.player_id = this._pagePlayer;
    } else if (mode === "filter") {
      if (!this._pageRole && !this._pageNeocorp) {
        this._feedback("Pick a role and/or NeoCorp", "warn");
        return;
      }
      if (this._pageRole) payload.role = this._pageRole;
      if (this._pageNeocorp) payload.neocorp = this._pageNeocorp;
    }

    try {
      await this.hass!.callService("digital_node_nexus", "page", payload);
      this._feedback("Page sent", "ok");
    } catch (err) {
      this._feedback("Page failed: " + this._formatErr(err), "err");
    }
  }

  async _sendLed() {
    const target = this._requireDeviceOrAll(this._ledTarget);
    if (!target) return;
    const payload = {
      ...target,
      state: this._ledState === "true",
      effect: this._ledEffect,
      brightness: Number(this._ledBrightness || 255),
      r: Number(this._ledR || 0),
      g: Number(this._ledG || 0),
      b: Number(this._ledB || 0),
    };
    try {
      await this.hass!.callService("digital_node_nexus", "set_led", payload);
      this._feedback("LED command sent", "ok");
    } catch (err) {
      this._feedback("LED failed: " + this._formatErr(err), "err");
    }
  }

  async _sendHaptic() {
    const target = this._requireDeviceOrAll(this._hapticTarget);
    if (!target) return;
    const payload = {
      ...target,
      pattern: this._hapticPattern,
      intensity: Number(this._hapticIntensity || 255),
      duration_ms: Number(this._hapticDuration || 100),
      repeat: Number(this._hapticRepeat || 1),
    };
    try {
      await this.hass!.callService(
        "digital_node_nexus",
        "trigger_haptic",
        payload
      );
      this._feedback("Haptic command sent", "ok");
    } catch (err) {
      this._feedback("Haptic failed: " + this._formatErr(err), "err");
    }
  }

  override render() {
    const html = window.McPanel.html;
    const mode = this._pageTargetMode;
    return html`
      <div class="wrap">
        <header class="page-header">
          <h1>Digital Node Nexus</h1>
          <div class="header-actions">
            ${this._feedbackTemplate()}
            <button class="btn btn-secondary" @click=${() => this._refresh()}>
              Refresh
            </button>
          </div>
        </header>

        <div class="tabs">
          <button
            class="tab ${this._tab === "page" ? "active" : ""}"
            @click=${() => {
              this._tab = "page";
            }}
          >
            Page
          </button>
          <button
            class="tab ${this._tab === "led" ? "active" : ""}"
            @click=${() => {
              this._tab = "led";
            }}
          >
            LED
          </button>
          <button
            class="tab ${this._tab === "haptic" ? "active" : ""}"
            @click=${() => {
              this._tab = "haptic";
            }}
          >
            Haptic
          </button>
        </div>

        <div class="card" style="margin-bottom:16px">
          <div class="card-header">FDNs</div>
          <div class="card-body">
            <div class="chip-row">
              ${this._devices.length
                ? this._devices.map((d) => {
                    const selected =
                      d.device_id === this._selectedDevice ? " selected" : "";
                    const presence = d.presence || "unknown";
                    return html`<button
                      type="button"
                      class="chip${selected}"
                      @click=${() => {
                        this._selectedDevice = d.device_id;
                      }}
                    >
                      <span class="dot ${presence}"></span>${d.device_id}
                      (${presence})
                    </button>`;
                  })
                : html`<span class="hint"
                    >No devices yet — waiting for mc/dnn/status/…</span
                  >`}
            </div>
          </div>
        </div>

        <div class="card ${this._tab !== "page" ? "hidden" : ""}">
          <div class="card-header">Page</div>
          <div class="card-body">
            <div class="form-grid">
              <div class="field wide">
                <label for="page-message">Message</label>
                <textarea
                  id="page-message"
                  placeholder="Message to page…"
                  .value=${this._pageMessage}
                  @input=${(e: Event) => {
                    this._pageMessage = (e.target as HTMLTextAreaElement).value;
                  }}
                ></textarea>
              </div>
              <div class="field">
                <label for="page-target-mode">Target</label>
                <select
                  id="page-target-mode"
                  .value=${this._pageTargetMode}
                  @change=${(e: Event) => {
                    this._pageTargetMode = (
                      e.target as HTMLSelectElement
                    ).value;
                  }}
                >
                  <option value="device">Selected FDN</option>
                  <option value="all">All FDNs</option>
                  <option value="broadcast">Broadcast Group</option>
                  <option value="player">Player</option>
                  <option value="filter">Role / NeoCorp filter</option>
                </select>
              </div>
              <div
                class="field ${mode !== "broadcast" ? "hidden" : ""}"
              >
                <label for="page-broadcast">Broadcast Group ID</label>
                <input
                  id="page-broadcast"
                  type="text"
                  autocomplete="off"
                  .value=${this._pageBroadcast}
                  @input=${(e: Event) => {
                    this._pageBroadcast = (
                      e.target as HTMLInputElement
                    ).value;
                  }}
                />
              </div>
              <div class="field ${mode !== "player" ? "hidden" : ""}">
                <label for="page-player">Player</label>
                <select
                  id="page-player"
                  .value=${this._pagePlayer}
                  @change=${(e: Event) => {
                    this._pagePlayer = (e.target as HTMLSelectElement).value;
                  }}
                >
                  <option value="">Select player…</option>
                  ${this._players.map((p) => {
                    const id = p.id || "";
                    const name = p.name || id;
                    return html`<option value=${id}>
                      ${name} (${p.role || ""}/${p.neocorp || ""})
                    </option>`;
                  })}
                </select>
              </div>
              <div class="field ${mode !== "filter" ? "hidden" : ""}">
                <label for="page-role">Role</label>
                <select
                  id="page-role"
                  .value=${this._pageRole}
                  @change=${(e: Event) => {
                    this._pageRole = (e.target as HTMLSelectElement).value;
                  }}
                >
                  <option value="">(any)</option>
                  <option value="hunter">Hunter</option>
                  <option value="bounty">Bounty</option>
                </select>
              </div>
              <div class="field ${mode !== "filter" ? "hidden" : ""}">
                <label for="page-neocorp">NeoCorp</label>
                <select
                  id="page-neocorp"
                  .value=${this._pageNeocorp}
                  @change=${(e: Event) => {
                    this._pageNeocorp = (e.target as HTMLSelectElement).value;
                  }}
                >
                  <option value="">(any)</option>
                  <option value="freelancer">Freelancer</option>
                  <option value="helix">Helix</option>
                  <option value="endline">Endline</option>
                  <option value="reboot">Reboot</option>
                </select>
              </div>
              <div class="field">
                <label for="page-duration">Duration (s)</label>
                <input
                  id="page-duration"
                  type="number"
                  min="1"
                  max="60"
                  .value=${String(this._pageDuration)}
                  @input=${(e: Event) => {
                    this._pageDuration = Number(
                      (e.target as HTMLInputElement).value || 10
                    );
                  }}
                />
              </div>
              <div class="field">
                <label for="page-scroll">Scroll</label>
                <select
                  id="page-scroll"
                  .value=${this._pageScroll}
                  @change=${(e: Event) => {
                    this._pageScroll = (e.target as HTMLSelectElement).value;
                  }}
                >
                  <option value="false">No</option>
                  <option value="true">Yes</option>
                </select>
              </div>
              <div class="field">
                <button
                  class="btn btn-primary"
                  @click=${() => this._sendPage()}
                >
                  Send Page
                </button>
              </div>
            </div>
            <p class="hint">
              Paging starts a state machine on the FDN. Player / filter stamps
              travel in the payload; until placement exists they route on
              cmd/all. Broker: official Mosquitto add-on via HA mqtt.
            </p>
          </div>
        </div>

        <div class="card ${this._tab !== "led" ? "hidden" : ""}">
          <div class="card-header">LED</div>
          <div class="card-body">
            <div class="form-grid">
              <div class="field">
                <label for="led-target">Target</label>
                <select
                  id="led-target"
                  .value=${this._ledTarget}
                  @change=${(e: Event) => {
                    this._ledTarget = (e.target as HTMLSelectElement).value;
                  }}
                >
                  <option value="device">Selected FDN</option>
                  <option value="all">All FDNs</option>
                </select>
              </div>
              <div class="field">
                <label for="led-state">State</label>
                <select
                  id="led-state"
                  .value=${this._ledState}
                  @change=${(e: Event) => {
                    this._ledState = (e.target as HTMLSelectElement).value;
                  }}
                >
                  <option value="true">On</option>
                  <option value="false">Off</option>
                </select>
              </div>
              <div class="field">
                <label for="led-effect">Effect</label>
                <select
                  id="led-effect"
                  .value=${this._ledEffect}
                  @change=${(e: Event) => {
                    this._ledEffect = (e.target as HTMLSelectElement).value;
                  }}
                >
                  <option value="solid">Solid</option>
                  <option value="blink">Blink</option>
                  <option value="pulse">Pulse</option>
                  <option value="rainbow">Rainbow</option>
                </select>
              </div>
              <div class="field">
                <label for="led-brightness">Brightness</label>
                <input
                  id="led-brightness"
                  type="number"
                  min="0"
                  max="255"
                  .value=${String(this._ledBrightness)}
                  @input=${(e: Event) => {
                    this._ledBrightness = Number(
                      (e.target as HTMLInputElement).value || 255
                    );
                  }}
                />
              </div>
              <div class="field">
                <label for="led-r">R</label>
                <input
                  id="led-r"
                  type="number"
                  min="0"
                  max="255"
                  .value=${String(this._ledR)}
                  @input=${(e: Event) => {
                    this._ledR = Number(
                      (e.target as HTMLInputElement).value || 0
                    );
                  }}
                />
              </div>
              <div class="field">
                <label for="led-g">G</label>
                <input
                  id="led-g"
                  type="number"
                  min="0"
                  max="255"
                  .value=${String(this._ledG)}
                  @input=${(e: Event) => {
                    this._ledG = Number(
                      (e.target as HTMLInputElement).value || 0
                    );
                  }}
                />
              </div>
              <div class="field">
                <label for="led-b">B</label>
                <input
                  id="led-b"
                  type="number"
                  min="0"
                  max="255"
                  .value=${String(this._ledB)}
                  @input=${(e: Event) => {
                    this._ledB = Number(
                      (e.target as HTMLInputElement).value || 0
                    );
                  }}
                />
              </div>
              <div class="field">
                <button
                  class="btn btn-primary"
                  @click=${() => this._sendLed()}
                >
                  Set LED
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="card ${this._tab !== "haptic" ? "hidden" : ""}">
          <div class="card-header">Haptic</div>
          <div class="card-body">
            <div class="form-grid">
              <div class="field">
                <label for="haptic-target">Target</label>
                <select
                  id="haptic-target"
                  .value=${this._hapticTarget}
                  @change=${(e: Event) => {
                    this._hapticTarget = (
                      e.target as HTMLSelectElement
                    ).value;
                  }}
                >
                  <option value="device">Selected FDN</option>
                  <option value="all">All FDNs</option>
                </select>
              </div>
              <div class="field">
                <label for="haptic-pattern">Pattern</label>
                <select
                  id="haptic-pattern"
                  .value=${this._hapticPattern}
                  @change=${(e: Event) => {
                    this._hapticPattern = (
                      e.target as HTMLSelectElement
                    ).value;
                  }}
                >
                  <option value="short">Short</option>
                  <option value="long">Long</option>
                  <option value="double">Double</option>
                  <option value="sos">SOS</option>
                  <option value="custom">Custom</option>
                </select>
              </div>
              <div class="field">
                <label for="haptic-intensity">Intensity</label>
                <input
                  id="haptic-intensity"
                  type="number"
                  min="0"
                  max="255"
                  .value=${String(this._hapticIntensity)}
                  @input=${(e: Event) => {
                    this._hapticIntensity = Number(
                      (e.target as HTMLInputElement).value || 255
                    );
                  }}
                />
              </div>
              <div class="field">
                <label for="haptic-duration">Duration (ms)</label>
                <input
                  id="haptic-duration"
                  type="number"
                  min="1"
                  max="5000"
                  .value=${String(this._hapticDuration)}
                  @input=${(e: Event) => {
                    this._hapticDuration = Number(
                      (e.target as HTMLInputElement).value || 100
                    );
                  }}
                />
              </div>
              <div class="field">
                <label for="haptic-repeat">Repeat</label>
                <input
                  id="haptic-repeat"
                  type="number"
                  min="1"
                  max="20"
                  .value=${String(this._hapticRepeat)}
                  @input=${(e: Event) => {
                    this._hapticRepeat = Number(
                      (e.target as HTMLInputElement).value || 1
                    );
                  }}
                />
              </div>
              <div class="field">
                <button
                  class="btn btn-primary"
                  @click=${() => this._sendHaptic()}
                >
                  Trigger Haptic
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }
}

customElements.define("dnn-panel", DnnPanel);
