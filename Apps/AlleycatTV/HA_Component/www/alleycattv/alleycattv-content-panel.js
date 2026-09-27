/**
 * AlleycatTV Content Manager panel — proxies content APIs through HA.
 *
 * Uses /api/alleycattv/proxy/… only (HA session auth). No direct LAN fetch.
 */
class AlleycatTVContentPanel extends window.McPanel.Base {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._groups = [];
    this._content = [];
  }

  set hass(hass) {
    super.hass = hass;
  }
  get hass() {
    return super.hass;
  }

  async _proxy(path, options = {}) {
    const url = `/api/alleycattv/proxy/${path.replace(/^\//, "")}`;
    const resp = await this.hass.fetchWithAuth(url, {
      method: options.method || "GET",
      headers: options.body
        ? { "Content-Type": "application/json" }
        : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(text || `HTTP ${resp.status}`);
    }
    const ct = resp.headers.get("content-type") || "";
    if (ct.includes("application/json")) return resp.json();
    return resp.text();
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        ${window.McPanel.Base.sharedStyles()}
        .btn { padding: 8px 18px; border-radius: 6px; border: none; cursor: pointer; font-size: 0.9rem; }
        .btn-primary { background: var(--primary-color, #3d85c8); color: #fff; }
        .btn-secondary { background: var(--secondary-background-color, #1e2a45); color: var(--primary-text-color); }
        table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid var(--divider-color, #2a3555); }
        .hint { color: var(--secondary-text-color); font-size: 0.85rem; }
        .row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
      </style>
      <div class="wrap">
        <header class="page-header">
          <h1>AlleycatTV Content</h1>
          <div class="header-actions">
            <span id="feedback" class="feedback"></span>
            <button class="btn btn-secondary" id="refresh-btn">Refresh</button>
          </div>
        </header>
        <p class="hint">Proxied through Home Assistant. Full manage UI also available at the content server /manage (ops).</p>
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">Broadcast groups (playlists)</div>
          <div class="card-body">
            <div id="groups"><span class="hint">Loading…</span></div>
          </div>
        </div>
        <div class="card">
          <div class="card-header">Content library</div>
          <div class="card-body">
            <div id="content"><span class="hint">Loading…</span></div>
          </div>
        </div>
      </div>
    `;
    this.shadowRoot.getElementById("refresh-btn").onclick = () => this._boot();
  }

  async _boot() {
    if (!this.hass) return;
    try {
      const [groups, content] = await Promise.all([
        this._proxy("api/broadcast_groups/").catch(() =>
          this._proxy("api/zones/")
        ),
        this._proxy("api/content/"),
      ]);
      this._groups = Array.isArray(groups) ? groups : [];
      this._content = Array.isArray(content) ? content : [];
      this._paint();
      this._feedback("Refreshed", "ok");
    } catch (err) {
      this._feedback(String(err), "err");
    }
  }

  _paint() {
    const gEl = this.shadowRoot.getElementById("groups");
    if (!this._groups.length) {
      gEl.innerHTML = `<span class="hint">No broadcast groups yet.</span>`;
    } else {
      gEl.innerHTML = `<table><thead><tr><th>ID</th><th>Name</th></tr></thead><tbody>
        ${this._groups
          .map((g) => {
            const id = this._esc(g.broadcast_group_id || g.zone_id || "");
            const name = this._esc(g.name || "");
            return `<tr><td>${id}</td><td>${name}</td></tr>`;
          })
          .join("")}
      </tbody></table>`;
    }
    const cEl = this.shadowRoot.getElementById("content");
    if (!this._content.length) {
      cEl.innerHTML = `<span class="hint">No media files yet.</span>`;
    } else {
      cEl.innerHTML = `<table><thead><tr><th>File</th><th>Type</th></tr></thead><tbody>
        ${this._content
          .slice(0, 100)
          .map((f) => {
            const name = this._esc(f.filename || f.name || f.path || JSON.stringify(f));
            const typ = this._esc(f.media_type || f.subdir || "");
            return `<tr><td>${name}</td><td>${typ}</td></tr>`;
          })
          .join("")}
      </tbody></table>`;
    }
  }

  connectedCallback() {
    this._render();
    this._boot();
  }
}

customElements.define("alleycattv-content-panel", AlleycatTVContentPanel);
