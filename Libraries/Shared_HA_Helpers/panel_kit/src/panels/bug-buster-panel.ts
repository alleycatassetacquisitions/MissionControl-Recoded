/// <reference path="../mc-panel/globals.d.ts" />
// @ts-nocheck — legacyPaint port preserves imperative panel logic
/**
 * Bug Buster — Mission Control ops panel.
 *
 * Guest picker from Proxmox (console only; monitoring is HA Core Proxmox VE),
 * MQTT spy, companion /health, in-browser termproxy console (xterm.js).
 * Proxmox URL/tokens: Core Configurator. Deploy: config/www/bug_buster/
 */
class BugBusterPanel extends window.McPanel.Base {
  constructor() {
    super();
    this.legacyPaint = true;
    this._panel = null;
    this._hosts = [];
    this._selected = null;
    this._mqtt = [];
    this._mqttPaused = false;
    this._mqttFilter = "";
    this._mqttCount = 0;
    this._mqttWindow = [];
    this._polledAt = null;
    this._proxmoxError = null;
    this._proxmoxErrorKind = null;
    this._proxmoxUrl = "";
    this._proxmoxNode = "";
    this._inventory = {};
    this._health = [];
    this._unsubs = [];
    this._termUnsub = null;
    this._term = null;
    this._fit = null;
    this._termConnected = false;
    this._termVmid = null;
    this._resizeObs = null;
  }

  set panel(p) {
    this._panel = p;
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._teardown();
  }

  async _boot() {
    this._bind();
    await this._loadHosts();
    await this._loadMqtt();
    await this._loadHealth();
    await this._subscribe();
  }

  _teardown() {
    for (const unsub of this._unsubs) {
      try { unsub(); } catch (_) { /* ignore */ }
    }
    this._unsubs = [];
    this._closeTerm(true);
    if (this._resizeObs) {
      this._resizeObs.disconnect();
      this._resizeObs = null;
    }
  }

  async _ws(type, extra = {}) {
    return this.hass.connection.sendMessagePromise({ type, ...extra });
  }

  async _loadHosts() {
    try {
      const res = await this._ws("bug_buster/list_hosts");
      this._hosts = res.hosts || [];
      this._polledAt = res.polled_at;
      this._proxmoxError = res.proxmox_error;
      this._proxmoxErrorKind = res.proxmox_error_kind || (this._proxmoxError ? "other" : null);
      this._mqttCount = res.mqtt_count || this._mqttCount;
      if (res.proxmox_url) this._proxmoxUrl = res.proxmox_url;
      if (res.proxmox_node != null) this._proxmoxNode = res.proxmox_node;
      if (res.inventory) this._inventory = res.inventory;
      if (Array.isArray(res.health)) this._health = res.health;
      this._paintHosts();
      this._paintHealth();
      this._paintHeader();
    } catch (err) {
      this._proxmoxError = err.message || String(err);
      this._proxmoxErrorKind = "other";
      this._paintHeader();
    }
  }

  async _loadHealth() {
    try {
      const res = await this._ws("bug_buster/health");
      this._health = res.health || [];
      this._paintHealth();
    } catch (err) {
      console.warn("[Bug Buster] health failed", err);
    }
  }

  async _loadMqtt() {
    try {
      const res = await this._ws("bug_buster/mqtt_snapshot");
      this._mqtt = res.messages || [];
      this._mqttCount = res.received || this._mqtt.length;
      this._paintMqtt(true);
      this._paintHeader();
    } catch (err) {
      console.warn("[Bug Buster] mqtt snapshot failed", err);
    }
  }

  async _subscribe() {
    if (!this.hass) return;
    try {
      this._unsubs.push(await this.hass.connection.subscribeEvents((ev) => {
        const d = ev.data || {};
        this._hosts = d.hosts || [];
        this._polledAt = d.polled_at;
        this._proxmoxError = d.proxmox_error || null;
        this._proxmoxErrorKind = d.proxmox_error_kind || (this._proxmoxError ? "other" : null);
        if (d.inventory) this._inventory = d.inventory;
        this._paintHosts();
        this._paintHeader();
      }, "bug_buster_hosts_update"));
    } catch (err) {
      console.warn("[Bug Buster] hosts subscribe failed", err);
    }
    try {
      this._unsubs.push(await this.hass.connection.subscribeEvents((ev) => {
        const item = ev.data;
        if (!item || !item.topic) return;
        this._mqttCount += 1;
        this._mqttWindow.push(Date.now());
        if (!this._mqttPaused) {
          this._mqtt.push(item);
          if (this._mqtt.length > 200) this._mqtt.shift();
          this._appendMqtt(item);
        }
        this._paintHeader();
      }, "bug_buster_mqtt_message"));
    } catch (err) {
      console.warn("[Bug Buster] mqtt subscribe failed", err);
    }
  }

  _bind() {
    const root = this.shadowRoot;
    root.getElementById("mqtt-pause")?.addEventListener("click", () => {
      this._mqttPaused = !this._mqttPaused;
      const btn = root.getElementById("mqtt-pause");
      if (btn) btn.textContent = this._mqttPaused ? "Resume" : "Pause";
    });
    root.getElementById("mqtt-clear")?.addEventListener("click", () => {
      this._mqtt = [];
      this._paintMqtt(true);
    });
    root.getElementById("mqtt-filter")?.addEventListener("input", (ev) => {
      this._mqttFilter = ev.target.value.trim();
      this._paintMqtt(true);
    });
    root.getElementById("term-connect")?.addEventListener("click", () => this._connectTerm());
    root.getElementById("term-disconnect")?.addEventListener("click", () => this._closeTerm());
    root.getElementById("host-refresh")?.addEventListener("click", () => this._loadHosts());
    root.getElementById("health-refresh")?.addEventListener("click", () => this._loadHealth());
  }

  _paintHealth() {
    const el = this.shadowRoot.getElementById("health-list");
    if (!el) return;
    if (!this._health.length) {
      el.innerHTML = `<p class="empty">No companion health yet.</p>`;
      return;
    }
    el.innerHTML = this._health.map((h) => {
      const ok = !!h.ok;
      const status = h.status != null ? `HTTP ${h.status}` : (h.error || "—");
      return `<div class="health-row ${ok ? "ok" : "bad"}">
        <strong>${this._esc(h.key)}</strong>
        <span>${this._esc(status)}</span>
        <span class="muted">${this._esc(h.url || "not configured")}</span>
      </div>`;
    }).join("");
  }

  _hostByVmid(vmid) {
    return this._hosts.find((h) => Number(h.vmid) === Number(vmid));
  }

  _selectHost(vmid) {
    this._selected = Number(vmid);
    this._paintHosts();
    const host = this._hostByVmid(vmid);
    const label = this.shadowRoot.getElementById("term-host");
    if (label) {
      label.textContent = host ? `${host.name} (CT ${host.vmid})` : "No host selected";
    }
  }

  async _ensureXterm() {
    if (window.Terminal) return;
    await this._loadScript("/local/bug_buster/vendor/xterm.js");
    await this._loadScript("/local/bug_buster/vendor/xterm-addon-fit.js");
  }

  _loadScript(src) {
    return new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[data-bug_buster="${src}"]`);
      if (existing) {
        existing.addEventListener("load", () => resolve());
        if (existing.dataset.loaded === "1") resolve();
        return;
      }
      const s = document.createElement("script");
      s.src = src;
      s.dataset.bug_buster = src;
      s.onload = () => { s.dataset.loaded = "1"; resolve(); };
      s.onerror = () => reject(new Error(`Failed to load ${src}`));
      document.head.appendChild(s);
    });
  }

  async _connectTerm() {
    if (!this._selected) {
      this._feedback("Select an LXC first", "warn");
      return;
    }
    const host = this._hostByVmid(this._selected);
    if (!host) {
      this._feedback("Unknown host", "warn");
      return;
    }
    if (!host.online) {
      this._feedback("Container is offline", "warn");
      return;
    }
    await this._closeTerm(true);
    try {
      await this._ensureXterm();
    } catch (err) {
      this._feedback(`xterm failed to load: ${err.message}`, "error");
      return;
    }
    const Term = window.Terminal?.Terminal || window.Terminal;
    if (!Term) {
      this._feedback("xterm.js did not load", "error");
      return;
    }
    const hold = this.shadowRoot.getElementById("xterm");
    hold.innerHTML = "";
    const term = new Term({
      cursorBlink: true,
      fontFamily: '"Share Tech Mono", ui-monospace, monospace',
      fontSize: 14,
      theme: {
        background: "#070b14",
        foreground: "#b8f5d0",
        cursor: "#00e5ff",
        selectionBackground: "rgba(0, 229, 255, 0.25)",
      },
    });
    const FitCtor = window.FitAddon?.FitAddon || window.FitAddon;
    const fit = FitCtor ? new FitCtor() : null;
    if (fit) term.loadAddon(fit);
    term.open(hold);
    this._term = term;
    this._fit = fit;
    this._fitNow();
    if (this._resizeObs) this._resizeObs.disconnect();
    this._resizeObs = new ResizeObserver(() => this._fitNow());
    this._resizeObs.observe(hold);

    const cols = term.cols || 80;
    const rows = term.rows || 24;
    try {
      this._termUnsub = await this.hass.connection.subscribeMessage(
        (ev) => this._onTermEvent(ev),
        { type: "bug_buster/term_open", vmid: host.vmid, node: host.node, kind: host.kind || "lxc", cols, rows }
      );
      this._termConnected = true;
      this._termVmid = host.vmid;
      term.onData((data) => {
        if (!this._termConnected) return;
        this.hass.connection.sendMessage({ type: "bug_buster/term_data", data });
      });
      this._setTermState(`Connected · ${host.name}`);
      this._feedback(`Console opened on ${host.name}`, "ok");
    } catch (err) {
      this._feedback(`Console failed: ${err.message}`, "error");
      this._setTermState("Disconnected");
    }
  }

  _fitNow() {
    if (!this._term) return;
    try { this._fit?.fit(); } catch (_) { /* ignore */ }
    if (this._termConnected) {
      this.hass.connection.sendMessage({
        type: "bug_buster/term_resize",
        cols: this._term.cols,
        rows: this._term.rows,
      });
    }
  }

  _onTermEvent(ev) {
    if (!ev) return;
    if (ev.closed) {
      this._termConnected = false;
      this._setTermState("Disconnected");
      this._feedback("Console closed", "warn");
      return;
    }
    if (ev.data_b64 && this._term) {
      try {
        const bin = Uint8Array.from(atob(ev.data_b64), (c) => c.charCodeAt(0));
        this._term.write(bin);
      } catch (_) {
        this._term.write(ev.data_b64);
      }
    }
  }

  async _closeTerm(silent = false) {
    if (this._termUnsub) {
      try { this._termUnsub(); } catch (_) { /* ignore */ }
      this._termUnsub = null;
    }
    if (this.hass) {
      try { await this._ws("bug_buster/term_close"); } catch (_) { /* ignore */ }
    }
    this._termConnected = false;
    this._termVmid = null;
    if (this._term) {
      try { this._term.dispose(); } catch (_) { /* ignore */ }
      this._term = null;
    }
    this._fit = null;
    const hold = this.shadowRoot?.getElementById("xterm");
    if (hold) hold.innerHTML = "";
    this._setTermState("Disconnected");
    if (!silent) this._feedback("Console disconnected", "ok");
  }

  _setTermState(text) {
    const el = this.shadowRoot.getElementById("term-state");
    if (el) el.textContent = text;
  }

  _feedback(msg, kind = "ok") {
    const el = this.shadowRoot.getElementById("feedback");
    if (!el) return;
    el.textContent = msg;
    el.className = `feedback ${kind}`;
  }

  _paintHeader() {
    const root = this.shadowRoot;
    const poll = root.getElementById("poll-meta");
    if (poll) {
      const when = this._polledAt ? new Date(this._polledAt * 1000).toLocaleTimeString() : "never";
      const host = this._proxmoxUrl ? this._proxmoxUrl.replace(/^https?:\/\//, "") : "Proxmox";
      const errLabel = {
        auth: "token rejected",
        connect: "unreachable",
        other: this._proxmoxError ? "error" : "",
      }[this._proxmoxErrorKind] || (this._proxmoxError ? "error" : "");
      poll.textContent = errLabel ? `${host} · ${when} · ${errLabel}` : `${host} · ${when}`;
      poll.classList.toggle("error", Boolean(this._proxmoxError));
    }
    const hostCount = root.getElementById("host-count");
    if (hostCount) {
      const online = this._hosts.filter((h) => h.online).length;
      hostCount.textContent = `${online}/${this._hosts.length} online`;
    }
    const mqttMeta = root.getElementById("mqtt-meta");
    if (mqttMeta) {
      const cutoff = Date.now() - 5000;
      this._mqttWindow = this._mqttWindow.filter((t) => t > cutoff);
      mqttMeta.textContent = `${this._mqttCount} msgs · ${(this._mqttWindow.length / 5).toFixed(1)}/s`;
    }
  }

  _emptyFleet() {
    if (this._proxmoxErrorKind === "auth") {
      const host = this._esc((this._proxmoxUrl || "").replace(/^https?:\/\//, "") || "this address");
      return `<div class="empty error">
        <strong>Proxmox rejected the API token</strong>
        <p>The hypervisor at ${host} is up. Set <code>token_id</code> and <code>token_secret</code> on the Proxmox card in <strong>Core Configurator</strong> (id looks like <code>hass@pve!missioncontrol</code>).</p>
        <p>Create the token in Proxmox: Datacenter → Permissions → API Tokens. Paste the same secret into HA Core Proxmox VE for monitoring.</p>
      </div>`;
    }
    if (this._proxmoxError) {
      return `<div class="empty error">
        <strong>Could not list guests</strong>
        <p>${this._esc(this._proxmoxError)}</p>
      </div>`;
    }
    if (!this._polledAt) {
      return `<p class="empty">Waiting for Proxmox guest list…</p>`;
    }
    const counts = this._inventory || {};
    const parts = Object.keys(counts).sort().map((k) => `${k}: ${counts[k]}`);
    const seen = parts.length ? parts.join(", ") : "no cluster resources";
    return `<div class="empty error">
      <strong>Proxmox is up, but no guests are visible</strong>
      <p>The token reached ${this._esc((this._proxmoxUrl || "").replace(/^https?:\/\//, "") || "Proxmox")} and got a reply (${this._esc(seen)}).</p>
      <p>If Privilege Separation is enabled on the token, grant <code>PVEAuditor</code> (or higher) on <code>/</code>, then refresh.</p>
    </div>`;
  }

  _paintHosts() {
    const list = this.shadowRoot.getElementById("host-grid");
    if (!list) return;
    if (!this._hosts.length) {
      list.innerHTML = this._emptyFleet();
      return;
    }
    list.innerHTML = this._hosts.map((h) => {
      const selected = Number(h.vmid) === Number(this._selected) ? " selected" : "";
      const online = h.online ? "online" : "offline";
      return `
        <button class="host-card ${online}${selected}" data-vmid="${h.vmid}">
          <div class="host-top">
            <span class="pip ${online}"></span>
            <strong>${this._esc(h.name)}</strong>
            <span class="ctid">${h.kind === "qemu" ? "VM" : "CT"} ${h.vmid}</span>
          </div>
          <div class="host-meta">
            <span>${h.online ? "Online" : "Offline"}</span>
            <span>${this._esc(h.node || "")}</span>
            <span>${this._esc(h.status || "")}</span>
          </div>
        </button>`;
    }).join("");
    list.querySelectorAll(".host-card").forEach((btn) => {
      btn.addEventListener("click", () => this._selectHost(btn.dataset.vmid));
      btn.addEventListener("dblclick", () => {
        this._selectHost(btn.dataset.vmid);
        this._connectTerm();
      });
    });
    const label = this.shadowRoot.getElementById("term-host");
    if (label && this._selected) {
      const host = this._hostByVmid(this._selected);
      if (host) label.textContent = `${host.name} (CT ${host.vmid})`;
    }
  }

  _mqttMatch(item) {
    if (!this._mqttFilter) return true;
    const q = this._mqttFilter.toLowerCase();
    return String(item.topic || "").toLowerCase().includes(q)
      || String(item.text || "").toLowerCase().includes(q);
  }

  _paintMqtt(rebuild) {
    const log = this.shadowRoot.getElementById("mqtt-log");
    if (!log) return;
    if (rebuild) {
      const rows = this._mqtt.filter((m) => this._mqttMatch(m));
      log.innerHTML = rows.length
        ? rows.map((m) => this._mqttRow(m)).join("")
        : `<p class="empty">No MQTT messages yet.</p>`;
      log.scrollTop = log.scrollHeight;
    }
  }

  _appendMqtt(item) {
    if (!this._mqttMatch(item)) return;
    const log = this.shadowRoot.getElementById("mqtt-log");
    if (!log) return;
    const empty = log.querySelector(".empty");
    if (empty) empty.remove();
    log.insertAdjacentHTML("beforeend", this._mqttRow(item));
    const near = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
    if (near) log.scrollTop = log.scrollHeight;
    while (log.children.length > 200) log.removeChild(log.firstChild);
  }

  _mqttRow(item) {
    const ts = item.ts ? new Date(item.ts * 1000).toLocaleTimeString() : "";
    const kind = item.kind || "text";
    const retain = item.retain ? " retain" : "";
    const extra = item.hex ? `\n${item.hex}` : "";
    return `<div class="mqtt-row ${kind}${retain}">
      <span class="ts">${this._esc(ts)}</span>
      <span class="topic">${this._esc(item.topic)}</span>
      <span class="kind">${this._esc(kind)}</span>
      <pre class="payload">${this._esc(item.text || "")}${this._esc(extra)}</pre>
    </div>`;
  }

  _fmtBytes(n) {
    const v = Number(n) || 0;
    if (v < 1024) return `${v} B`;
    const units = ["KB", "MB", "GB", "TB"];
    let x = v / 1024;
    let i = 0;
    while (x >= 1024 && i < units.length - 1) { x /= 1024; i += 1; }
    return `${x.toFixed(x >= 10 ? 0 : 1)} ${units[i]}`;
  }

  _fmtUptime(sec) {
    let s = Math.max(0, Number(sec) || 0);
    const d = Math.floor(s / 86400); s -= d * 86400;
    const h = Math.floor(s / 3600); s -= h * 3600;
    const m = Math.floor(s / 60);
    if (d) return `${d}d ${h}h`;
    if (h) return `${h}h ${m}m`;
    return `${m}m`;
  }

  _esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        @import url("/local/bug_buster/alleycat-panel.css");
        @import url("/local/bug_buster/vendor/xterm.css");
        :host {
          display: block;
          height: 100%;
          background: var(--primary-background-color, #0b1020);
          color: var(--primary-text-color, #e8eefc);
          overflow: hidden;
        }
        .wrap {
          display: flex;
          flex-direction: column;
          height: 100%;
          min-height: 0;
        }
        .page-header {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 14px 20px;
          flex-shrink: 0;
        }
        .page-header h1 { margin: 0; font-size: 20px; }
        .subtitle { margin: 2px 0 0; font-size: 12px; color: var(--secondary-text-color, #9aa8c7); letter-spacing: 0.08em; }
        .stats { margin-left: auto; display: flex; gap: 16px; font-size: 12px; color: var(--ac-cyan, #00e5ff); }
        .stats .error { color: #ff6b8a; }
        .feedback { font-size: 12px; min-height: 16px; }
        .feedback.ok { color: #7dffb3; }
        .feedback.warn { color: #ef9f27; }
        .feedback.error { color: #ff6b8a; }
        .settings-gear {
          margin-left: 8px;
          background: transparent;
          color: var(--secondary-text-color, #9aa8c7);
          border: 1px solid var(--divider-color, #1f3a44);
          border-radius: 6px;
          cursor: pointer;
          font-size: 18px;
          line-height: 1;
          padding: 6px 8px;
        }
        .settings-gear:hover { color: var(--ac-cyan, #00e5ff); border-color: var(--ac-cyan, #00e5ff); }
        .modal-overlay {
          position: fixed; inset: 0; background: rgba(0,0,0,0.65);
          display: flex; align-items: center; justify-content: center; z-index: 1000;
        }
        .modal-overlay[hidden] { display: none; }
        .modal-card {
          background: var(--card-background-color, #10151c);
          border: 1px solid var(--divider-color, #1f3a44);
          border-radius: 10px;
          padding: 24px;
          width: 400px;
          max-width: 95vw;
        }
        .modal-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
        .modal-header h3 { margin: 0; font-size: 14px; letter-spacing: 0.1em; text-transform: uppercase; }
        .modal-close {
          margin: 0; padding: 4px 8px; font-size: 16px; line-height: 1;
          background: transparent; color: var(--secondary-text-color, #7aa8b8);
          border: none; cursor: pointer;
        }
        .modal-card label { display: block; font-size: 12px; margin: 10px 0 4px; color: #9aa8c7; }
        .modal-card input {
          width: 100%; box-sizing: border-box; font-family: inherit;
          background: #0d1426; color: inherit; border: 1px solid #2a3a5c;
          border-radius: 6px; padding: 8px 10px;
        }
        .modal-hint { font-size: 11px; color: #9aa8c7; margin: 8px 0 0; }
        .modal-actions { display: flex; gap: 8px; margin-top: 18px; }
        .modal-actions button { flex: 1; }
        .modal-actions .ghost { margin-left: 0; }
        .body {
          flex: 1;
          min-height: 0;
          display: grid;
          grid-template-columns: 1.2fr 1fr;
          grid-template-rows: 1fr 280px;
          gap: 12px;
          padding: 0 16px 16px;
        }
        .hosts { grid-column: 1 / -1; min-height: 0; display: flex; flex-direction: column; }
        .mqtt, .term {
          min-height: 0;
          display: flex;
          flex-direction: column;
          background: var(--card-background-color, #12192e);
          border: 1px solid var(--divider-color, #2a3a5c);
          border-radius: 10px;
        }
        .hosts-head, .pane-head {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 14px;
          border-bottom: 1px solid var(--divider-color, #2a3a5c);
          font-size: 12px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--ac-cyan, #00e5ff);
        }
        .hosts-head button, .pane-head button, .pane-head input {
          font-family: inherit;
        }
        .ghost {
          margin-left: auto;
          background: transparent;
          color: var(--ac-cyan, #00e5ff);
          border: 1px solid rgba(0, 229, 255, 0.35);
          border-radius: 6px;
          padding: 4px 10px;
          cursor: pointer;
        }
        #host-grid {
          overflow: auto;
          padding: 12px;
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
          gap: 10px;
        }
        .host-card {
          text-align: left;
          background: #0d1426;
          color: inherit;
          border: 1px solid #2a3a5c;
          border-radius: 10px;
          padding: 12px;
          cursor: pointer;
          font-family: inherit;
        }
        .host-card.selected { border-color: var(--ac-cyan, #00e5ff); box-shadow: 0 0 12px rgba(0,229,255,0.25); }
        .host-card.offline { opacity: 0.7; }
        .host-top { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
        .host-top strong { flex: 1; }
        .ctid { font-size: 11px; color: var(--secondary-text-color, #9aa8c7); }
        .pip { width: 9px; height: 9px; border-radius: 50%; background: #ff6b8a; box-shadow: 0 0 8px #ff6b8a; }
        .pip.online { background: #7dffb3; box-shadow: 0 0 8px #7dffb3; }
        .bars label { display: flex; justify-content: space-between; font-size: 11px; color: #9aa8c7; }
        .bar { height: 6px; background: #1a2440; border-radius: 99px; margin: 3px 0 8px; overflow: hidden; }
        .bar i { display: block; height: 100%; background: linear-gradient(90deg, var(--ac-cyan, #00e5ff), var(--ac-magenta, #ff2bd6)); }
        .host-meta { display: flex; justify-content: space-between; font-size: 11px; color: #9aa8c7; gap: 6px; }
        #mqtt-log, #xterm { flex: 1; min-height: 0; overflow: auto; }
        #xterm { height: 100%; }
        #mqtt-log { padding: 8px 12px; font-size: 12px; }
        .mqtt-row { display: grid; grid-template-columns: 72px 1fr 64px; gap: 6px 10px; padding: 6px 0; border-bottom: 1px solid #1a2440; }
        .mqtt-row .payload { grid-column: 1 / -1; margin: 0; white-space: pre-wrap; word-break: break-word; color: #b8f5d0; font-size: 11px; }
        .mqtt-row .topic { color: var(--ac-cyan, #00e5ff); }
        .mqtt-row .kind { text-transform: uppercase; font-size: 10px; color: #9aa8c7; text-align: right; }
        .mqtt-row.binary .kind { color: #ff2bd6; }
        .mqtt-row.retain .topic::after { content: " ●"; color: #ef9f27; }
        .pane-head input {
          margin-left: auto;
          background: #0d1426;
          color: inherit;
          border: 1px solid #2a3a5c;
          border-radius: 6px;
          padding: 4px 8px;
          width: 160px;
        }
        #xterm { background: #070b14; padding: 6px; }
        .empty { color: #9aa8c7; padding: 24px; text-align: center; }
        .empty.error { color: #ffb0c0; max-width: 640px; margin: 24px auto; text-align: left; }
        .empty.error strong { display: block; margin-bottom: 8px; color: #ff6b8a; letter-spacing: 0.08em; text-transform: uppercase; font-size: 12px; }
        .empty.error p { margin: 8px 0; line-height: 1.45; }
        .empty.error pre {
          margin: 10px 0; padding: 10px 12px; background: #0d1426; border: 1px solid #2a3a5c;
          border-radius: 6px; color: #b8f5d0; overflow: auto; font-size: 12px;
        }
        .empty.error code { color: #00e5ff; }
        .term-actions { display: flex; gap: 8px; margin-left: auto; align-items: center; }
        #term-host, #term-state { text-transform: none; letter-spacing: 0; color: #9aa8c7; font-size: 11px; }
        .health-row {
          display: grid; grid-template-columns: 160px 120px 1fr; gap: 8px;
          padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.06); font-size: 13px;
        }
        .health-row.ok strong { color: #7dffb3; }
        .health-row.bad strong { color: #ff6b8a; }
        .health-row .muted { color: #9aa8c7; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .cc-note { font-size: 12px; color: #9aa8c7; margin: 0 16px 0 0; max-width: 280px; }
        @media (max-width: 980px) {
          .body { grid-template-columns: 1fr; grid-template-rows: auto auto auto auto; }
          .hosts { max-height: 320px; }
          .health-row { grid-template-columns: 1fr; }
        }
      </style>
      <div class="wrap">
        <header class="page-header">
          <div>
            <h1>Bug Buster</h1>
            <p class="subtitle">Proxmox console · MQTT spy · companion health</p>
          </div>
          <div class="stats">
            <span id="host-count">0/0 online</span>
            <span id="poll-meta">Proxmox never</span>
            <span id="mqtt-meta">0 msgs</span>
          </div>
          <p class="cc-note">Proxmox URL and API token: Core Configurator. Monitoring entities: HA Proxmox VE integration.</p>
          <span id="feedback" class="feedback"></span>
        </header>
        <div class="body">
          <section class="hosts mqtt">
            <div class="hosts-head">
              <span>Guests (console)</span>
              <button class="ghost" id="host-refresh" type="button">Refresh</button>
            </div>
            <div id="host-grid"><p class="empty">Waiting for Proxmox guest list…</p></div>
          </section>
          <section class="mqtt">
            <div class="pane-head">
              <span>Companion health</span>
              <button class="ghost" id="health-refresh" type="button">Refresh</button>
            </div>
            <div id="health-list"><p class="empty">No companion health yet.</p></div>
          </section>
          <section class="mqtt">
            <div class="pane-head">
              <span>MQTT</span>
              <input id="mqtt-filter" type="text" placeholder="filter topic…" />
              <button class="ghost" id="mqtt-pause" type="button">Pause</button>
              <button class="ghost" id="mqtt-clear" type="button">Clear</button>
            </div>
            <div id="mqtt-log"><p class="empty">No MQTT messages yet.</p></div>
          </section>
          <section class="term">
            <div class="pane-head">
              <span>Console</span>
              <span id="term-host">No host selected</span>
              <span id="term-state">Disconnected</span>
              <div class="term-actions">
                <button class="ghost" id="term-connect" type="button">Connect</button>
                <button class="ghost" id="term-disconnect" type="button">Disconnect</button>
              </div>
            </div>
            <div id="xterm"></div>
          </section>
        </div>
      </div>
    `;
  }
}

if (!customElements.get("bug-buster-panel")) {
  customElements.define("bug-buster-panel", BugBusterPanel);
}
