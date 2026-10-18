"use strict";
(() => {
  // src/panels/core-configurator-panel.ts
  var CoreConfiguratorPanel = class extends window.McPanel.Base {
    constructor() {
      super();
      this._unsub = null;
      this._services = [];
      this._loaded = false;
      this._netTimeBusy = false;
      this._netTimeOnline = null;
      this._netTimePublic = null;
      this._netTimeDetail = "";
    }
    static get properties() {
      return {
        ...super.properties,
        _services: { state: true },
        _loaded: { state: true },
        _netTimeBusy: { state: true },
        _netTimeOnline: { state: true },
        _netTimePublic: { state: true },
        _netTimeDetail: { state: true }
      };
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
        .net-time-ops {
          margin-top: 12px;
          padding-top: 12px;
          border-top: 1px solid
            color-mix(in srgb, var(--primary-color, #00e5ff) 18%, transparent);
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .net-time-ops .ops-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          align-items: center;
        }
        .net-time-status {
          font-size: 12px;
          color: var(--secondary-text-color, #9aa8c7);
          line-height: 1.4;
        }
        .net-time-status strong {
          color: var(--primary-text-color, #e8eefc);
          font-weight: 600;
        }
        .net-time-status.ok strong {
          color: #7dffa3;
        }
        .net-time-status.warn strong {
          color: #ffd27d;
        }
        .net-time-status.err strong {
          color: #ff8a8a;
        }
      `
      ];
    }
    _cc() {
      return typeof window !== "undefined" && window.CoreConfigurator || null;
    }
    async _boot() {
      await this._load();
      const cc = this._cc();
      if (cc?.subscribe) {
        this._unsub = await cc.subscribe(this.hass, () => this._load());
      }
    }
    disconnectedCallback() {
      if (this._unsub) {
        try {
          this._unsub();
        } catch (_) {
        }
        this._unsub = null;
      }
      super.disconnectedCallback();
    }
    async _load() {
      const cc = this._cc();
      try {
        this._services = cc ? await cc.getServices(this.hass) : (await this.hass.connection.sendMessagePromise({
          type: "core_configurator/get_services"
        })).services || [];
        this._loaded = true;
      } catch (err) {
        this._loaded = true;
        const e = err;
        this._feedback(`Load failed: ${e.message || err}`, "err");
        return;
      }
    }
    async _save(card) {
      const key = card.dataset.key;
      if (!key) return;
      const url = (card.querySelector(".url")?.value || "").trim();
      const extra = {};
      card.querySelectorAll("[data-extra]").forEach((inp) => {
        const el = inp;
        if (el.dataset.kind === "checkbox") {
          extra[el.dataset.extra] = el.checked ? "true" : "false";
        } else {
          extra[el.dataset.extra] = el.value.trim();
        }
      });
      const cc = this._cc();
      try {
        if (cc) {
          await cc.setService(this.hass, key, { url, extra });
        } else {
          await this.hass.connection.sendMessagePromise({
            type: "core_configurator/set_service",
            key,
            url,
            extra
          });
        }
        this._feedback(`Saved ${key}`, "ok");
        await this._load();
      } catch (err) {
        const e = err;
        this._feedback(`Save failed: ${e.message || err}`, "err");
      }
    }
    async _netTimeConfirm() {
      if (!this.hass || this._netTimeBusy) return;
      this._netTimeBusy = true;
      this._netTimeDetail = "Checking\u2026";
      try {
        await this.hass.connection.sendMessagePromise({
          type: "net_time/health"
        });
        this._netTimeOnline = true;
        const status = await this.hass.connection.sendMessagePromise({
          type: "net_time/status"
        });
        this._netTimePublic = status.public_ntp || "unavailable";
        const publicLabel = this._netTimePublic === "reachable" ? "able to connect to public NTP" : "no public NTP available";
        this._netTimeDetail = `Online with MC \xB7 ${publicLabel}${status.stratum != null ? ` \xB7 stratum ${status.stratum}` : ""}${status.iso ? ` \xB7 ${status.iso}` : ""}`;
        this._feedback("Net Time reachable", "ok");
      } catch (err) {
        this._netTimeOnline = false;
        this._netTimePublic = null;
        const e = err;
        this._netTimeDetail = e.message || String(err);
        this._feedback(`Net Time offline: ${e.message || err}`, "err");
      } finally {
        this._netTimeBusy = false;
      }
    }
    async _netTimeSyncNow() {
      if (!this.hass || this._netTimeBusy) return;
      this._netTimeBusy = true;
      this._netTimeDetail = "Syncing from this PC\u2026";
      try {
        const iso8601 = (/* @__PURE__ */ new Date()).toISOString();
        const result = await this.hass.connection.sendMessagePromise({
          type: "net_time/sync",
          iso8601
        });
        this._netTimeOnline = true;
        this._netTimePublic = result.status?.public_ntp || "unavailable";
        this._netTimeDetail = `Synced to ${result.applied_iso || iso8601} \xB7 no public NTP available`;
        this._feedback("Net Time synced from this PC", "ok");
      } catch (err) {
        const e = err;
        this._netTimeDetail = e.message || String(err);
        this._feedback(`Sync failed: ${e.message || err}`, "err");
      } finally {
        this._netTimeBusy = false;
      }
    }
    _renderNetTimeOps() {
      const html = window.McPanel.html;
      const online = this._netTimeOnline;
      const pub = this._netTimePublic;
      const cls = online === false ? "err" : pub === "reachable" ? "ok" : online ? "warn" : "";
      const showSync = online === true && pub === "unavailable";
      return html`
      <div class="net-time-ops">
        <div class="ops-row">
          <button
            type="button"
            class="ghost"
            ?disabled=${this._netTimeBusy}
            @click=${() => void this._netTimeConfirm()}
          >
            Confirm online
          </button>
          ${showSync ? html`
                <button
                  type="button"
                  class="save"
                  ?disabled=${this._netTimeBusy}
                  @click=${() => void this._netTimeSyncNow()}
                >
                  Sync Now
                </button>
              ` : window.McPanel.nothing}
        </div>
        <p class="net-time-status ${cls}">
          ${this._netTimeDetail ? html`<strong>${this._netTimeDetail}</strong>` : html`Save URL + token, then Confirm online.`}
        </p>
      </div>
    `;
    }
    _renderExtras(svc) {
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
    render() {
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
          ${!this._loaded ? html`<p class="empty">Loading…</p>` : !this._services.length ? html`<p class="empty">
                No services loaded. Check that Core Configurator is configured.
              </p>` : this._services.map((svc) => {
        const empty = !svc.url;
        const apps = (svc.apps || []).join(" \xB7 ");
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
                        @click=${(e) => {
          const card = e.target.closest(
            ".card"
          );
          if (card) void this._save(card);
        }}
                      >
                        Apply
                      </button>
                      <span class="key">${svc.key}</span>
                      ${empty ? html`<span class="badge-empty">not set</span>` : window.McPanel.nothing}
                    </div>
                    ${svc.key === "net_time" ? this._renderNetTimeOps() : window.McPanel.nothing}
                  </article>
                `;
      })}
        </div>
      </div>
    `;
    }
  };
  customElements.define("core-configurator-panel", CoreConfiguratorPanel);
})();
//# sourceMappingURL=core-configurator-panel.js.map
