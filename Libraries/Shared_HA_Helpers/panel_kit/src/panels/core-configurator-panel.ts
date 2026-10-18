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

/** Common venue / event IANA zones for the Net Time dropdown. */
const NET_TIME_TIMEZONES: { value: string; label: string }[] = [
  { value: "UTC", label: "UTC" },
  { value: "America/New_York", label: "US Eastern (New York)" },
  { value: "America/Chicago", label: "US Central (Chicago)" },
  { value: "America/Denver", label: "US Mountain (Denver)" },
  { value: "America/Phoenix", label: "US Arizona (Phoenix, no DST)" },
  { value: "America/Los_Angeles", label: "US Pacific (Los Angeles)" },
  { value: "America/Anchorage", label: "US Alaska (Anchorage)" },
  { value: "Pacific/Honolulu", label: "US Hawaii (Honolulu)" },
  { value: "America/Toronto", label: "Canada Eastern (Toronto)" },
  { value: "America/Winnipeg", label: "Canada Central (Winnipeg)" },
  { value: "America/Edmonton", label: "Canada Mountain (Edmonton)" },
  { value: "America/Vancouver", label: "Canada Pacific (Vancouver)" },
  { value: "America/Mexico_City", label: "Mexico (Mexico City)" },
  { value: "America/Sao_Paulo", label: "Brazil (São Paulo)" },
  { value: "Europe/London", label: "UK (London)" },
  { value: "Europe/Dublin", label: "Ireland (Dublin)" },
  { value: "Europe/Paris", label: "Central Europe (Paris)" },
  { value: "Europe/Berlin", label: "Central Europe (Berlin)" },
  { value: "Europe/Amsterdam", label: "Central Europe (Amsterdam)" },
  { value: "Europe/Madrid", label: "Spain (Madrid)" },
  { value: "Europe/Rome", label: "Italy (Rome)" },
  { value: "Europe/Warsaw", label: "Poland (Warsaw)" },
  { value: "Europe/Athens", label: "Greece (Athens)" },
  { value: "Europe/Moscow", label: "Russia (Moscow)" },
  { value: "Africa/Johannesburg", label: "South Africa (Johannesburg)" },
  { value: "Asia/Dubai", label: "UAE (Dubai)" },
  { value: "Asia/Kolkata", label: "India (Kolkata)" },
  { value: "Asia/Bangkok", label: "Thailand (Bangkok)" },
  { value: "Asia/Singapore", label: "Singapore" },
  { value: "Asia/Hong_Kong", label: "Hong Kong" },
  { value: "Asia/Shanghai", label: "China (Shanghai)" },
  { value: "Asia/Tokyo", label: "Japan (Tokyo)" },
  { value: "Asia/Seoul", label: "Korea (Seoul)" },
  { value: "Australia/Perth", label: "Australia Western (Perth)" },
  { value: "Australia/Adelaide", label: "Australia Central (Adelaide)" },
  { value: "Australia/Sydney", label: "Australia Eastern (Sydney)" },
  { value: "Pacific/Auckland", label: "New Zealand (Auckland)" },
];

class CoreConfiguratorPanel extends window.McPanel.Base {
  static get properties() {
    return {
      ...super.properties,
      _services: { state: true },
      _loaded: { state: true },
      _netTimeBusy: { state: true },
      _netTimeOnline: { state: true },
      _netTimePublic: { state: true },
      _netTimeDetail: { state: true },
      _netTimeTimezone: { state: true },
    };
  }

  declare _services: CcService[];
  declare _loaded: boolean;
  declare _netTimeBusy: boolean;
  /** null = not checked yet */
  declare _netTimeOnline: boolean | null;
  /** reachable | unavailable | null */
  declare _netTimePublic: string | null;
  declare _netTimeDetail: string;
  declare _netTimeTimezone: string;
  private _unsub: (() => void) | null = null;

  constructor() {
    super();
    this._services = [];
    this._loaded = false;
    this._netTimeBusy = false;
    this._netTimeOnline = null;
    this._netTimePublic = null;
    this._netTimeDetail = "";
    this._netTimeTimezone = "";
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

  async _netTimeConfirm() {
    if (!this.hass || this._netTimeBusy) return;
    this._netTimeBusy = true;
    this._netTimeDetail = "Checking…";
    try {
      await this.hass.connection.sendMessagePromise({
        type: "net_time/health",
      });
      this._netTimeOnline = true;
      const status = (await this.hass.connection.sendMessagePromise({
        type: "net_time/status",
      })) as {
        public_ntp?: string;
        stratum?: number;
        iso?: string;
        timezone?: string;
      };
      this._netTimePublic = status.public_ntp || "unavailable";
      if (status.timezone) this._netTimeTimezone = status.timezone;
      const publicLabel =
        this._netTimePublic === "reachable"
          ? "able to connect to public NTP"
          : "no public NTP available";
      const whenLabel = this._formatNetTimeClock(
        status.iso,
        status.timezone || this._netTimeTimezone
      );
      this._netTimeDetail = `Online with MC · ${publicLabel}${
        status.stratum != null ? ` · stratum ${status.stratum}` : ""
      }${whenLabel ? ` · ${whenLabel}` : ""}`;
      this._feedback("Net Time reachable", "ok");
    } catch (err) {
      this._netTimeOnline = false;
      this._netTimePublic = null;
      const e = err as { message?: string };
      this._netTimeDetail = e.message || String(err);
      this._feedback(`Net Time offline: ${e.message || err}`, "err");
    } finally {
      this._netTimeBusy = false;
    }
  }

  async _netTimeSyncNow() {
    if (!this.hass || this._netTimeBusy) return;
    this._netTimeBusy = true;
    this._netTimeDetail = "Syncing from this PC…";
    try {
      const iso8601 = new Date().toISOString();
      const result = (await this.hass.connection.sendMessagePromise({
        type: "net_time/sync",
        iso8601,
      })) as {
        applied_iso?: string;
        via?: string;
        status?: { public_ntp?: string; stratum?: number; timezone?: string };
      };
      this._netTimeOnline = true;
      this._netTimePublic = result.status?.public_ntp || this._netTimePublic;
      if (result.status?.timezone) this._netTimeTimezone = result.status.timezone;
      const via = result.via === "host" ? "via Proxmox host" : "local";
      this._netTimeDetail = `Synced to ${result.applied_iso || iso8601} (${via})`;
      this._feedback("Net Time synced from this PC", "ok");
    } catch (err) {
      const e = err as { message?: string };
      this._netTimeDetail = e.message || String(err);
      this._feedback(`Sync failed: ${e.message || err}`, "err");
    } finally {
      this._netTimeBusy = false;
    }
  }

  /** Format server ISO (UTC) as local wall time in the configured timezone. */
  _formatNetTimeClock(iso?: string, timeZone?: string): string {
    if (!iso) return "";
    const ms = Date.parse(iso);
    if (Number.isNaN(ms)) return iso;
    const tz = (timeZone || "").trim() || "UTC";
    try {
      const local = new Intl.DateTimeFormat("en-US", {
        timeZone: tz,
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: true,
      }).format(new Date(ms));
      return `${local} (${tz})`;
    } catch {
      return `${iso} (UTC)`;
    }
  }

  async _netTimeSetTimezone(card: HTMLElement) {
    if (!this.hass || this._netTimeBusy) return;
    const select = card.querySelector(
      "#net-time-timezone"
    ) as HTMLSelectElement | null;
    const timezone = (select?.value || this._netTimeTimezone || "").trim();
    if (!timezone) {
      this._feedback("Choose a timezone from the list", "err");
      return;
    }
    this._netTimeBusy = true;
    this._netTimeDetail = `Setting timezone ${timezone}…`;
    try {
      const result = (await this.hass.connection.sendMessagePromise({
        type: "net_time/set_timezone",
        timezone,
      })) as { timezone?: string; status?: { public_ntp?: string } };
      this._netTimeTimezone = result.timezone || timezone;
      if (select) select.value = this._netTimeTimezone;
      this._netTimeDetail = `Timezone set to ${this._netTimeTimezone}`;
      this._feedback(`Timezone ${this._netTimeTimezone}`, "ok");
    } catch (err) {
      const e = err as { message?: string };
      this._netTimeDetail = e.message || String(err);
      this._feedback(`Timezone failed: ${e.message || err}`, "err");
    } finally {
      this._netTimeBusy = false;
    }
  }

  _netTimeTimezoneOptions() {
    const html = window.McPanel.html;
    const current = this._netTimeTimezone || "";
    const known = new Set(NET_TIME_TIMEZONES.map((z) => z.value));
    const options = [...NET_TIME_TIMEZONES];
    if (current && !known.has(current)) {
      options.unshift({ value: current, label: `${current} (current)` });
    }
    const selected = current || "America/Chicago";
    return options.map(
      (z) => html`
        <option value=${z.value} ?selected=${z.value === selected}>
          ${z.label}
        </option>
      `
    );
  }

  _renderNetTimeOps() {
    const html = window.McPanel.html;
    const online = this._netTimeOnline;
    const pub = this._netTimePublic;
    const cls =
      online === false ? "err" : pub === "reachable" ? "ok" : online ? "warn" : "";
    return html`
      <div class="net-time-ops">
        <label for="net-time-timezone">Timezone</label>
        <select id="net-time-timezone">
          ${this._netTimeTimezoneOptions()}
        </select>
        <div class="ops-row">
          <button
            type="button"
            class="ghost"
            ?disabled=${this._netTimeBusy}
            @click=${() => void this._netTimeConfirm()}
          >
            Confirm online
          </button>
          <button
            type="button"
            class="ghost"
            ?disabled=${this._netTimeBusy}
            @click=${(e: Event) => {
              const card = (e.target as HTMLElement).closest(
                ".card"
              ) as HTMLElement | null;
              if (card) void this._netTimeSetTimezone(card);
            }}
          >
            Set timezone
          </button>
          <button
            type="button"
            class="save"
            ?disabled=${this._netTimeBusy}
            @click=${() => void this._netTimeSyncNow()}
          >
            Sync Now
          </button>
        </div>
        <p class="net-time-status ${cls}">
          ${this._netTimeDetail
            ? html`<strong>${this._netTimeDetail}</strong>`
            : html`Save URL + token, then Confirm online. Sync Now sets venue time from this PC (uses Proxmox host when the LXC cannot).`}
        </p>
      </div>
    `;
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
                    ${svc.key === "net_time"
                      ? this._renderNetTimeOps()
                      : window.McPanel.nothing}
                  </article>
                `;
              })}
        </div>
      </div>
    `;
  }
}

customElements.define("core-configurator-panel", CoreConfiguratorPanel);
