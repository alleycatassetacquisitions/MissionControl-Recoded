/// <reference path="../mc-panel/globals.d.ts" />
/**
 * Game Master panel — gameplay controls via MCS → Central.
 *
 * Registration owns event create/set-active and players.
 * This panel reads game-state and toggles scoring / delayed scores.
 */

type GmEvent = {
  id?: string;
  name?: string;
  venue_name?: string | null;
  created_at?: string;
};

type GmScoring = {
  enabled?: boolean;
  started_at?: string | null;
};

type GmState = {
  active_event?: GmEvent | null;
  scoring?: GmScoring | null;
  accepting_delayed_scores?: boolean | null;
  server_time_utc?: string;
};

class GameMasterPanel extends window.McPanel.Base {
  static get properties() {
    return {
      ...super.properties,
      _state: { state: true },
      _busy: { state: true },
    };
  }

  declare _state: GmState | null;
  declare _busy: boolean;

  constructor() {
    super();
    this._state = null;
    this._busy = false;
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
      `,
    ];
  }

  _formatErr(err: unknown): string {
    if (err == null) return "unknown error";
    if (typeof err === "string") return err;
    const e = err as {
      message?: string;
      error?: string | { message?: string };
      code?: string;
    };
    if (typeof e.error === "object" && e.error?.message) return e.error.message;
    if (typeof e.error === "string") return e.error;
    return e.message || e.code || JSON.stringify(err);
  }

  override async _boot() {
    await this._refresh();
  }

  async _refresh() {
    this._busy = true;
    try {
      const result = await this.hass!.callWS<GmState>({
        type: "game_master/get_game_state",
      });
      this._state = result || {};
      this._feedback("Game state refreshed", "ok");
    } catch (err) {
      this._state = null;
      this._feedback("Could not load game state: " + this._formatErr(err), "err");
    } finally {
      this._busy = false;
    }
  }

  async _setScoring(enabled: boolean) {
    this._busy = true;
    try {
      await this.hass!.callWS({
        type: "game_master/set_scoring",
        enabled,
      });
      this._feedback(enabled ? "Game live — scoring on" : "Scoring off", "ok");
      await this._refresh();
    } catch (err) {
      this._feedback("Scoring update failed: " + this._formatErr(err), "err");
      this._busy = false;
    }
  }

  async _setDelayed(enabled: boolean) {
    this._busy = true;
    try {
      await this.hass!.callWS({
        type: "game_master/set_delayed_scores",
        enabled,
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

  _activeLabel(): string {
    const ev = this._state?.active_event;
    if (!ev) return "None — select an event in Registration";
    const name = (ev.name || "").trim();
    const venue = (ev.venue_name || "").trim();
    if (name && venue) return `${name} · ${venue}`;
    return name || ev.id || "Unknown event";
  }

  _formatTime(value?: string | null): string {
    if (!value) return "";
    try {
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return value;
      return d.toLocaleString();
    } catch {
      return value;
    }
  }

  override render() {
    const html = window.McPanel.html;
    const state = this._state;
    const scoringOn = Boolean(state?.scoring?.enabled);
    const delayedOn = state?.accepting_delayed_scores !== false && state != null
      ? Boolean(state.accepting_delayed_scores)
      : false;
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
              ${this._formatTime(state?.server_time_utc) || "—"}
              ${scoringOn && state?.scoring?.started_at
                ? html` · Scoring since
                  ${this._formatTime(state.scoring.started_at)}`
                : ""}
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
                @change=${(e: Event) => {
                  const on = (e.target as HTMLInputElement).checked;
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
                @change=${(e: Event) => {
                  const on = (e.target as HTMLInputElement).checked;
                  this._setDelayed(on);
                }}
              />
              <span class="slider"></span>
            </label>
          </div>
          ${!hasActive
            ? html`<p class="meta" style="margin-top:12px">
                Set an active event in Registration before toggling gameplay.
              </p>`
            : ""}
        </section>

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
}

customElements.define("game-master-panel", GameMasterPanel);
