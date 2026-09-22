/**
 * Core Configurator sidebar panel — Mission Control source of truth for endpoints.
 * Deploy: config/www/core_configurator/
 */
class CoreConfiguratorPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._initialized = false;
    this._services = [];
    this._unsub = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._render();
      this._boot();
    }
  }

  connectedCallback() {
    if (this._hass && !this._initialized) {
      this._initialized = true;
      this._render();
      this._boot();
    }
  }

  disconnectedCallback() {
    this._initialized = false;
    if (this._unsub) {
      try { this._unsub(); } catch (_) { /* ignore */ }
      this._unsub = null;
    }
  }

  _cc() {
    return (typeof window !== "undefined" && window.CoreConfigurator) || null;
  }

  async _boot() {
    this.shadowRoot.getElementById("btn-reload")?.addEventListener("click", () => this._load());
    await this._load();
    const cc = this._cc();
    if (cc?.subscribe) {
      this._unsub = await cc.subscribe(this._hass, () => this._load());
    }
  }

  async _load() {
    const cc = this._cc();
    try {
      this._services = cc
        ? await cc.getServices(this._hass)
        : (await this._hass.connection.sendMessagePromise({
            type: "core_configurator/get_services",
          })).services || [];
    } catch (err) {
      this._feedback(`Load failed: ${err.message || err}`, "err");
      return;
    }
    this._paint();
  }

  _feedback(msg, kind = "ok") {
    const el = this.shadowRoot.getElementById("feedback");
    if (!el) return;
    el.textContent = msg;
    el.className = `feedback ${kind}`;
    if (kind === "ok") {
      clearTimeout(this._fbTimer);
      this._fbTimer = setTimeout(() => { el.textContent = ""; }, 3000);
    }
  }

  _esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  _paint() {
    const list = this.shadowRoot.getElementById("cards");
    if (!list) return;
    if (!this._services.length) {
      list.innerHTML = `<p class="empty">No services loaded. Check that Core Configurator is configured.</p>`;
      return;
    }
    list.innerHTML = this._services.map((svc) => {
      const extras = (svc.extra_fields || []).map((f) => {
        const raw = (svc.extra || {})[f.key] || "";
        return `
          <label for="extra-${this._esc(svc.key)}-${this._esc(f.key)}">${this._esc(f.label)}</label>
          <input id="extra-${this._esc(svc.key)}-${this._esc(f.key)}"
            data-extra="${this._esc(f.key)}"
            type="text" value="${this._esc(raw)}"
            placeholder="${this._esc(f.placeholder || "")}"
            autocomplete="off" />
        `;
      }).join("");

      const empty = !svc.url;
      const apps = (svc.apps || []).join(" · ");

      return `
        <article class="card ${empty ? "card--empty" : ""}" data-key="${this._esc(svc.key)}">
          <header>
            <h2>${this._esc(svc.label)}</h2>
            <span class="apps">${this._esc(apps)}</span>
          </header>
          <p class="hint">${this._esc(svc.hint || "")}</p>
          <label for="url-${this._esc(svc.key)}">URL or IP</label>
          <input id="url-${this._esc(svc.key)}" class="url" type="text"
            value="${this._esc(svc.url || "")}"
            placeholder="${this._esc(svc.placeholder || "")}" />
          ${extras}
          <div class="row">
            <button type="button" class="save">Apply</button>
            <span class="key">${this._esc(svc.key)}</span>
            ${empty ? `<span class="badge-empty">not set</span>` : ""}
          </div>
        </article>`;
    }).join("");

    list.querySelectorAll(".card").forEach((card) => {
      card.querySelector(".save")?.addEventListener("click", () => this._save(card));
    });
  }

  async _save(card) {
    const key = card.dataset.key;
    const url = (card.querySelector(".url")?.value || "").trim();
    const extra = {};
    card.querySelectorAll("[data-extra]").forEach((inp) => {
      extra[inp.dataset.extra] = inp.value.trim();
    });
    const cc = this._cc();
    try {
      if (cc) {
        await cc.setService(this._hass, key, { url, extra });
      } else {
        await this._hass.connection.sendMessagePromise({
          type: "core_configurator/set_service",
          key,
          url,
          extra,
        });
      }
      this._feedback(`Saved ${key}`, "ok");
      await this._load();
    } catch (err) {
      this._feedback(`Save failed: ${err.message || err}`, "err");
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100%;
          overflow: auto;
          background: var(--primary-background-color, #0b1020);
          color: var(--primary-text-color, #e8eefc);
          font-family: var(--primary-font-family, system-ui, sans-serif);
        }
        .wrap { max-width: 980px; margin: 0 auto; padding: 1rem 1.25rem 3rem; }

        /* Page header */
        .page-header {
          display: flex; align-items: flex-end; gap: 16px;
          padding-bottom: 12px; margin-bottom: 20px;
          border-bottom: 1px solid rgba(255,255,255,0.08);
        }
        .page-header h1 { margin: 0; font-size: 20px; font-weight: 600; }
        .sub { margin: 4px 0 0; font-size: 13px; color: var(--secondary-text-color, #9aa8c7); }
        .header-actions { margin-left: auto; display: flex; align-items: center; gap: 12px; }

        /* Ghost button */
        .ghost {
          background: transparent;
          color: var(--primary-color, #00e5ff);
          border: 1px solid color-mix(in srgb, var(--primary-color, #00e5ff) 40%, transparent);
          border-radius: 6px; padding: 6px 12px; cursor: pointer;
          font-family: inherit; font-size: 13px;
        }
        .ghost:hover { background: color-mix(in srgb, var(--primary-color, #00e5ff) 10%, transparent); }

        /* Feedback */
        .feedback { font-size: 13px; min-height: 18px; }
        .feedback.ok { color: #7dffb3; }
        .feedback.err { color: #ff6b8a; }

        /* Cards grid */
        #cards {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
          gap: 14px;
        }
        .card {
          background: var(--card-background-color, #12192e);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 10px;
          padding: 16px;
        }
        .card--empty { border-color: rgba(255, 107, 107, 0.35); }
        .card h2 {
          margin: 0; font-size: 13px; font-weight: 600;
          letter-spacing: 0.05em; text-transform: uppercase;
        }
        .apps {
          display: block; font-size: 11px;
          color: var(--primary-color, #00e5ff); margin-top: 4px;
        }
        .hint { font-size: 12px; color: var(--secondary-text-color, #9aa8c7); margin: 8px 0 12px; }

        /* Inputs */
        label {
          display: block; font-size: 11px; letter-spacing: 0.05em;
          text-transform: uppercase; color: var(--secondary-text-color, #9aa8c7);
          margin: 10px 0 4px;
        }
        input {
          width: 100%; box-sizing: border-box; font-family: inherit; font-size: 14px;
          background: var(--secondary-background-color, #0d1426);
          color: var(--primary-text-color, #e8eefc);
          border: 1px solid rgba(255,255,255,0.12); border-radius: 6px;
          padding: 8px 10px;
          transition: border-color 0.15s;
        }
        input:focus { outline: none; border-color: var(--primary-color, #00e5ff); }

        /* Card footer row */
        .row { display: flex; align-items: center; gap: 10px; margin-top: 14px; }
        .save {
          background: var(--primary-color, #00e5ff);
          color: var(--primary-background-color, #041016);
          border: 0; border-radius: 6px; padding: 8px 16px;
          font-weight: 600; cursor: pointer; font-family: inherit; font-size: 13px;
        }
        .save:hover { opacity: 0.88; }
        .key { font-size: 11px; color: var(--secondary-text-color, #9aa8c7); }
        .badge-empty {
          margin-left: auto; font-size: 11px; font-weight: 600;
          color: #ff8a8a; letter-spacing: 0.05em; text-transform: uppercase;
        }

        .empty { color: var(--secondary-text-color, #9aa8c7); padding: 32px; text-align: center; }
      </style>
      <div class="wrap">
        <header class="page-header">
          <div>
            <h1>Core Configurator</h1>
            <p class="sub">
              Source of truth for Alleycat endpoints.
              Set an IP here — Registration, AlleycatTV, GBN, and Bug Buster follow.
            </p>
          </div>
          <div class="header-actions">
            <span id="feedback" class="feedback"></span>
            <button type="button" class="ghost" id="btn-reload">Reload</button>
          </div>
        </header>
        <div id="cards"><p class="empty">Loading…</p></div>
      </div>
    `;
  }
}

if (!customElements.get("core-configurator-panel")) {
  customElements.define("core-configurator-panel", CoreConfiguratorPanel);
}
