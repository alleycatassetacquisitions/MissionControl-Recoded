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
      _netTimeOfflineOpen: { state: true },
      _netTimeOfflineDate: { state: true },
      _netTimeOfflineTime: { state: true },
      _updateBusy: { state: true },
      _updateStatus: { state: true },
      _updateDetail: { state: true },
      _updateLastAt: { state: true },
      _updateLatest: { state: true },
      _updateChanged: { state: true },
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
  declare _netTimeOfflineOpen: boolean;
  declare _netTimeOfflineDate: string;
  declare _netTimeOfflineTime: string;
  declare _updateBusy: boolean;
  /** null | up_to_date | update_available | error | applying */
  declare _updateStatus: string | null;
  declare _updateDetail: string;
  declare _updateLastAt: string;
  declare _updateLatest: string;
  declare _updateChanged: string[];
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
    this._netTimeOfflineOpen = false;
    this._netTimeOfflineDate = "";
    this._netTimeOfflineTime = "";
    this._updateBusy = false;
    this._updateStatus = null;
    this._updateDetail = "";
    this._updateLastAt = "";
    this._updateLatest = "";
    this._updateChanged = [];
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
        .net-time-offline {
          margin-top: 8px;
          padding: 10px;
          border: 1px solid
            color-mix(in srgb, var(--primary-color, #00e5ff) 22%, transparent);
          border-radius: 6px;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .net-time-offline .offline-fields {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
        }
        @media (max-width: 420px) {
          .net-time-offline .offline-fields {
            grid-template-columns: 1fr;
          }
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

  _offlineSyncHint(): string {
    return "Please set via Offline Sync";
  }

  _seedOfflineDateTime(timeZone?: string) {
    const tz = (timeZone || this._netTimeTimezone || "").trim() || undefined;
    const now = new Date();
    const opts: Intl.DateTimeFormatOptions = {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    };
    try {
      const parts = new Intl.DateTimeFormat("en-CA", opts).formatToParts(now);
      const get = (t: string) => parts.find((p) => p.type === t)?.value || "";
      this._netTimeOfflineDate = `${get("year")}-${get("month")}-${get("day")}`;
      this._netTimeOfflineTime = `${get("hour")}:${get("minute")}`;
    } catch {
      this._netTimeOfflineDate = now.toISOString().slice(0, 10);
      this._netTimeOfflineTime = now.toISOString().slice(11, 16);
    }
  }

  _toggleOfflineSync() {
    this._netTimeOfflineOpen = !this._netTimeOfflineOpen;
    if (this._netTimeOfflineOpen && !this._netTimeOfflineDate) {
      this._seedOfflineDateTime();
    }
  }

  /**
   * Convert wall date+time in an IANA zone to UTC ISO-8601.
   * Iteratively corrects for DST / offset using Intl.
   */
  _wallTimeToUtcIso(date: string, time: string, timeZone: string): string {
    const dateBits = date.split("-").map((x) => Number(x));
    const timeBits = (time.length === 5 ? `${time}:00` : time)
      .split(":")
      .map((x) => Number(x));
    const y = dateBits[0];
    const mo = dateBits[1];
    const d = dateBits[2];
    const hh = timeBits[0] || 0;
    const mm = timeBits[1] || 0;
    const ss = timeBits[2] || 0;
    if (!y || !mo || !d) {
      throw new Error("Invalid date");
    }
    const wantUtc = Date.UTC(y, mo - 1, d, hh, mm, ss);
    let guess = wantUtc;
    const tz = timeZone.trim() || "UTC";
    for (let i = 0; i < 4; i++) {
      const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: tz,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hourCycle: "h23",
      }).formatToParts(new Date(guess));
      const get = (t: string) =>
        Number(parts.find((p) => p.type === t)?.value || "0");
      const asUtc = Date.UTC(
        get("year"),
        get("month") - 1,
        get("day"),
        get("hour"),
        get("minute"),
        get("second")
      );
      guess += wantUtc - asUtc;
    }
    return new Date(guess).toISOString();
  }

  async _venueUpdateCheck() {
    if (!this.hass || this._updateBusy) return;
    this._updateBusy = true;
    this._updateDetail = "Checking GitHub for updates…";
    try {
      const result = (await this.hass.connection.sendMessagePromise({
        type: "core_configurator/update_check",
      })) as {
        status?: string;
        detail?: string;
        installed_release?: string;
        latest_release?: string;
        latest_published_at?: string;
        last_updated_at?: string;
        summary?: string;
        changed_components?: string[];
      };
      this._updateStatus = result.status || "error";
      this._updateLastAt = result.last_updated_at || "";
      this._updateLatest =
        result.summary || result.latest_release || result.installed_release || "";
      this._updateChanged = result.changed_components || [];
      if (result.status === "up_to_date") {
        this._updateDetail = `Up to date with the latest release${
          this._updateLatest ? `: ${this._updateLatest}` : ""
        }${
          this._updateLastAt ? ` · last updated ${this._updateLastAt}` : ""
        }`;
        this._feedback("Up to date", "ok");
      } else if (result.status === "update_available") {
        const changed = this._updateChanged.length
          ? ` (${this._updateChanged.join(", ")})`
          : "";
        this._updateDetail = `Update available${changed}${
          this._updateLatest ? ` — ${this._updateLatest}` : ""
        }. Would you like to install?`;
        this._feedback("Update available", "ok");
      } else {
        this._updateDetail = result.detail || "Update check failed";
        this._feedback(this._updateDetail, "err");
      }
    } catch (err) {
      this._updateStatus = "error";
      const e = err as { message?: string };
      this._updateDetail = e.message || "Update check failed";
      this._feedback(this._updateDetail, "err");
    } finally {
      this._updateBusy = false;
    }
  }

  async _venueUpdateApply() {
    if (!this.hass || this._updateBusy) return;
    this._updateBusy = true;
    this._updateStatus = "applying";
    this._updateDetail = "Installing update on Proxmox host…";
    try {
      const started = (await this.hass.connection.sendMessagePromise({
        type: "core_configurator/update_apply",
      })) as { status?: string; detail?: string };
      if (started.status === "error") {
        this._updateStatus = "error";
        this._updateDetail = started.detail || "Apply failed to start";
        this._feedback(this._updateDetail, "err");
        return;
      }
      // Poll status until apply finishes
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const st = (await this.hass.connection.sendMessagePromise({
          type: "core_configurator/update_status",
        })) as {
          apply_running?: boolean;
          last_apply?: { status?: string; detail?: string; errors?: string[] };
          last_updated_at?: string;
          installed_release?: string;
        };
        if (st.apply_running) continue;
        const last = st.last_apply || {};
        this._updateLastAt = st.last_updated_at || this._updateLastAt;
        if (last.status === "ok" || (!last.errors?.length && last.status !== "error")) {
          this._updateStatus = "up_to_date";
          this._updateLatest = st.installed_release || this._updateLatest;
          this._updateChanged = [];
          this._updateDetail = `Up to date${
            this._updateLatest ? `: ${this._updateLatest}` : ""
          }${this._updateLastAt ? ` · last updated ${this._updateLastAt}` : ""}`;
          this._feedback("Update installed", "ok");
        } else {
          this._updateStatus = "error";
          this._updateDetail =
            last.detail ||
            (last.errors || []).join("; ") ||
            "Update apply failed";
          this._feedback(this._updateDetail, "err");
        }
        return;
      }
      this._updateStatus = "error";
      this._updateDetail = "Timed out waiting for apply — check Proxmox host";
      this._feedback(this._updateDetail, "err");
    } catch (err) {
      this._updateStatus = "error";
      const e = err as { message?: string };
      this._updateDetail = e.message || "Apply failed";
      this._feedback(this._updateDetail, "err");
    } finally {
      this._updateBusy = false;
    }
  }

  _renderVenueUpdateOps() {
    const html = window.McPanel.html;
    return html`
      <div class="ops" style="margin-top:0.75rem">
        <button
          type="button"
          ?disabled=${this._updateBusy}
          @click=${() => void this._venueUpdateCheck()}
        >
          Check for GitHub Update
        </button>
        ${this._updateStatus === "update_available"
          ? html`<button
              type="button"
              ?disabled=${this._updateBusy}
              @click=${() => void this._venueUpdateApply()}
            >
              Install update
            </button>`
          : window.McPanel.nothing}
        ${this._updateDetail
          ? html`<p class="hint" style="margin-top:0.5rem">${this._updateDetail}</p>`
          : window.McPanel.nothing}
      </div>
    `;
  }

  async _netTimeAttemptOnlineSync() {
    if (!this.hass || this._netTimeBusy) return;
    this._netTimeBusy = true;
    this._netTimeDetail = "Attempting online sync…";
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
      const whenLabel = this._formatNetTimeClock(
        status.iso,
        status.timezone || this._netTimeTimezone
      );
      if (this._netTimePublic === "reachable") {
        this._netTimeDetail = `Online sync OK · public NTP reachable${
          status.stratum != null ? ` · stratum ${status.stratum}` : ""
        }${whenLabel ? ` · ${whenLabel}` : ""}`;
        this._feedback("Online sync OK", "ok");
      } else {
        this._netTimeDetail = this._offlineSyncHint();
        this._netTimeOfflineOpen = true;
        this._seedOfflineDateTime(status.timezone || this._netTimeTimezone);
        this._feedback(this._offlineSyncHint(), "err");
      }
    } catch (err) {
      this._netTimeOnline = false;
      this._netTimePublic = null;
      this._netTimeDetail = this._offlineSyncHint();
      this._netTimeOfflineOpen = true;
      this._seedOfflineDateTime();
      const e = err as { message?: string };
      this._feedback(
        `${this._offlineSyncHint()}${e.message ? ` (${e.message})` : ""}`,
        "err"
      );
    } finally {
      this._netTimeBusy = false;
    }
  }

  async _netTimeApplyOfflineSync(card: HTMLElement) {
    if (!this.hass || this._netTimeBusy) return;
    const dateEl = card.querySelector(
      "#net-time-offline-date"
    ) as HTMLInputElement | null;
    const timeEl = card.querySelector(
      "#net-time-offline-time"
    ) as HTMLInputElement | null;
    const tzEl = card.querySelector(
      "#net-time-timezone"
    ) as HTMLSelectElement | null;
    const date = (dateEl?.value || this._netTimeOfflineDate || "").trim();
    const time = (timeEl?.value || this._netTimeOfflineTime || "").trim();
    const timeZone = (
      tzEl?.value ||
      this._netTimeTimezone ||
      "UTC"
    ).trim();
    if (!date || !time) {
      this._feedback("Choose a date and time for Offline Sync", "err");
      return;
    }
    this._netTimeBusy = true;
    this._netTimeDetail = "Applying Offline Sync…";
    try {
      const iso8601 = this._wallTimeToUtcIso(date, time, timeZone);
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
      this._netTimeOfflineDate = date;
      this._netTimeOfflineTime = time;
      const whenLabel = this._formatNetTimeClock(
        result.applied_iso || iso8601,
        this._netTimeTimezone || timeZone
      );
      this._netTimeDetail = `Offline Sync applied · ${whenLabel || iso8601}`;
      this._feedback("Offline Sync applied", "ok");
    } catch (err) {
      const e = err as { message?: string };
      this._netTimeDetail = e.message || String(err);
      this._feedback(`Offline Sync failed: ${e.message || err}`, "err");
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
      online === false
        ? "err"
        : pub === "reachable"
          ? "ok"
          : online
            ? "warn"
            : "";
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
            @click=${() => void this._netTimeAttemptOnlineSync()}
          >
            Attempt Online Sync
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
            @click=${() => this._toggleOfflineSync()}
          >
            Offline Sync
          </button>
        </div>
        ${this._netTimeOfflineOpen
          ? html`
              <div class="net-time-offline">
                <p class="hint">
                  Set venue date and time in the timezone above, then apply.
                  Use this when public NTP is unavailable.
                </p>
                <div class="offline-fields">
                  <div>
                    <label for="net-time-offline-date">Date</label>
                    <input
                      id="net-time-offline-date"
                      type="date"
                      .value=${this._netTimeOfflineDate}
                      @input=${(e: Event) => {
                        this._netTimeOfflineDate = (
                          e.target as HTMLInputElement
                        ).value;
                      }}
                    />
                  </div>
                  <div>
                    <label for="net-time-offline-time">Time</label>
                    <input
                      id="net-time-offline-time"
                      type="time"
                      step="1"
                      .value=${this._netTimeOfflineTime}
                      @input=${(e: Event) => {
                        this._netTimeOfflineTime = (
                          e.target as HTMLInputElement
                        ).value;
                      }}
                    />
                  </div>
                </div>
                <div class="ops-row">
                  <button
                    type="button"
                    class="save"
                    ?disabled=${this._netTimeBusy}
                    @click=${(e: Event) => {
                      const card = (e.target as HTMLElement).closest(
                        ".card"
                      ) as HTMLElement | null;
                      if (card) void this._netTimeApplyOfflineSync(card);
                    }}
                  >
                    Apply Offline Sync
                  </button>
                </div>
              </div>
            `
          : window.McPanel.nothing}
        <p class="net-time-status ${cls}">
          ${this._netTimeDetail
            ? html`<strong>${this._netTimeDetail}</strong>`
            : html`Save URL + token, then Attempt Online Sync. If that fails, use Offline Sync to set date and time.`}
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
                      : svc.key === "venue_updater"
                      ? this._renderVenueUpdateOps()
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
