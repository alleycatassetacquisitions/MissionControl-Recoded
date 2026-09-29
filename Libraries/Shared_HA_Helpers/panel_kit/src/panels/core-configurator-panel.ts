/// <reference path="../mc-panel/globals.d.ts" />
/**
 * Core Configurator sidebar panel — Mission Control source of truth for URLs and auth.
 * Deploy: config/www/core_configurator/
 */

type CcExtraField = {
  key: string;
  label: string;
  type?: string;
  sensitive?: boolean;
  placeholder?: string;
};

type CcService = {
  key: string;
  label: string;
  hint?: string;
  url?: string;
  placeholder?: string;
  apps?: string[];
  extra_fields?: CcExtraField[];
  extra?: Record<string, string>;
};

class CoreConfiguratorPanel extends window.McPanel.Base {
  static get properties() {
    return {
      ...super.properties,
      _services: { state: true },
      _loaded: { state: true },
    };
  }

  declare _services: CcService[];
  declare _loaded: boolean;
  private _unsub: (() => void) | null = null;

  constructor() {
    super();
    this._services = [];
    this._loaded = false;
  }

  static get styles() {
    const base = super.styles;
    const baseArr = Array.isArray(base) ? base : base ? [base] : [];
    return [
      ...baseArr,
      window.McPanel.css`
        #cards {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
          gap: 14px;
        }
        .card--empty {
          border-color: rgba(255, 107, 107, 0.35);
        }
        .apps {
          display: block;
          font-size: 11px;
          color: var(--primary-color, #00e5ff);
          margin-top: 4px;
        }
        label.check {
          display: flex;
          align-items: center;
          gap: 8px;
          text-transform: none;
          letter-spacing: 0;
          font-size: 13px;
          color: var(--primary-text-color, #e8eefc);
          margin-top: 12px;
        }
        label.check input {
          width: auto;
          margin: 0;
        }
        .ghost {
          background: transparent;
          color: var(--primary-color, #00e5ff);
          border: 1px solid
            color-mix(in srgb, var(--primary-color, #00e5ff) 40%, transparent);
          border-radius: 6px;
          padding: 6px 12px;
          cursor: pointer;
          font-family: inherit;
          font-size: 13px;
        }
        .ghost:hover {
          background: color-mix(
            in srgb,
            var(--primary-color, #00e5ff) 10%,
            transparent
          );
        }
        .save {
          background: var(--primary-color, #00e5ff);
          color: var(--primary-background-color, #041016);
          border: 0;
          border-radius: 6px;
          padding: 8px 16px;
          font-weight: 600;
          cursor: pointer;
          font-family: inherit;
          font-size: 13px;
        }
        .save:hover {
          opacity: 0.88;
        }
        .key {
          font-size: 11px;
          color: var(--secondary-text-color, #9aa8c7);
        }
        .badge-empty {
          margin-left: auto;
          font-size: 11px;
          font-weight: 600;
          color: #ff8a8a;
          letter-spacing: 0.05em;
          text-transform: uppercase;
        }
      `,
    ];
  }

  _cc() {
    return (
      (typeof window !== "undefined" && window.CoreConfigurator) || null
    );
  }

  override async _boot() {
    await this._load();
    const cc = this._cc();
    if (cc?.subscribe) {
      this._unsub = await cc.subscribe(this.hass, () => this._load());
    }
  }

  override disconnectedCallback() {
    if (this._unsub) {
      try {
        this._unsub();
      } catch (_) {
        /* ignore */
      }
      this._unsub = null;
    }
    super.disconnectedCallback();
  }

  async _load() {
    const cc = this._cc();
    try {
      this._services = cc
        ? ((await cc.getServices(this.hass)) as CcService[])
        : (
            (await this.hass!.connection.sendMessagePromise({
              type: "core_configurator/get_services",
            })) as { services?: CcService[] }
          ).services || [];
      this._loaded = true;
    } catch (err) {
      this._loaded = true;
      const e = err as { message?: string };
      this._feedback(`Load failed: ${e.message || err}`, "err");
      return;
    }
  }

  async _save(card: HTMLElement) {
    const key = card.dataset.key;
    if (!key) return;
    const url = (
      (card.querySelector(".url") as HTMLInputElement | null)?.value || ""
    ).trim();
    const extra: Record<string, string> = {};
    card.querySelectorAll("[data-extra]").forEach((inp) => {
      const el = inp as HTMLInputElement;
      if (el.dataset.kind === "checkbox") {
        extra[el.dataset.extra!] = el.checked ? "true" : "false";
      } else {
        extra[el.dataset.extra!] = el.value.trim();
      }
    });
    const cc = this._cc();
    try {
      if (cc) {
        await cc.setService(this.hass, key, { url, extra });
      } else {
        await this.hass!.connection.sendMessagePromise({
          type: "core_configurator/set_service",
          key,
          url,
          extra,
        });
      }
      this._feedback(`Saved ${key}`, "ok");
      await this._load();
    } catch (err) {
      const e = err as { message?: string };
      this._feedback(`Save failed: ${e.message || err}`, "err");
    }
  }

  _renderExtras(svc: CcService) {
    const html = window.McPanel.html;
    return (svc.extra_fields || []).map((f) => {
      const raw = (svc.extra || {})[f.key] || "";
      if (f.type === "checkbox") {
        const checked = String(raw).toLowerCase() === "true";
        return html`
          <label
            class="check"
            for=${`extra-${svc.key}-${f.key}`}
          >
            <input
              id=${`extra-${svc.key}-${f.key}`}
              data-extra=${f.key}
              data-kind="checkbox"
              type="checkbox"
              .checked=${checked}
            />
            ${f.label}
          </label>
        `;
      }
      const inputType = f.sensitive ? "password" : "text";
      return html`
        <label for=${`extra-${svc.key}-${f.key}`}>${f.label}</label>
        <input
          id=${`extra-${svc.key}-${f.key}`}
          data-extra=${f.key}
          type=${inputType}
          .value=${raw}
          placeholder=${f.placeholder || ""}
          autocomplete="off"
        />
      `;
    });
  }

  override render() {
    const html = window.McPanel.html;
    return html`
      <div class="wrap">
        <header class="page-header">
          <div>
            <h1>Core Configurator</h1>
            <p class="sub">
              Source of truth for Alleycat URLs and API tokens. Set them here —
              Registration, AlleycatTV, GBN, and Bug Buster follow.
            </p>
          </div>
          <div class="header-actions">
            ${this._feedbackTemplate()}
            <button
              type="button"
              class="ghost"
              @click=${() => this._load()}
            >
              Reload
            </button>
          </div>
        </header>
        <div id="cards">
          ${!this._loaded
            ? html`<p class="empty">Loading…</p>`
            : !this._services.length
            ? html`<p class="empty">
                No services loaded. Check that Core Configurator is configured.
              </p>`
            : this._services.map((svc) => {
                const empty = !svc.url;
                const apps = (svc.apps || []).join(" · ");
                return html`
                  <article
                    class="card ${empty ? "card--empty" : ""}"
                    data-key=${svc.key}
                  >
                    <header>
                      <h2>${svc.label}</h2>
                      <span class="apps">${apps}</span>
                    </header>
                    <p class="hint">${svc.hint || ""}</p>
                    <label for=${`url-${svc.key}`}>URL or IP</label>
                    <input
                      id=${`url-${svc.key}`}
                      class="url"
                      type="text"
                      .value=${svc.url || ""}
                      placeholder=${svc.placeholder || ""}
                    />
                    ${this._renderExtras(svc)}
                    <div class="row">
                      <button
                        type="button"
                        class="save"
                        @click=${(e: Event) => {
                          const card = (e.target as HTMLElement).closest(
                            ".card"
                          ) as HTMLElement | null;
                          if (card) void this._save(card);
                        }}
                      >
                        Apply
                      </button>
                      <span class="key">${svc.key}</span>
                      ${empty
                        ? html`<span class="badge-empty">not set</span>`
                        : window.McPanel.nothing}
                    </div>
                  </article>
                `;
              })}
        </div>
      </div>
    `;
  }
}

customElements.define("core-configurator-panel", CoreConfiguratorPanel);
