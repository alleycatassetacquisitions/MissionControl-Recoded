/// <reference path="../mc-panel/globals.d.ts" />
// @ts-nocheck — legacyPaint port preserves imperative panel logic
/**
 * Galactic Bounty Network — Mission Control capture + flavor editor.
 *
 * Roster: registration/get_roster websocket
 * API: GBN HTTP (flavor, intake, posters) via /api/gbn/proxy
 * Camera: getUserMedia + MediaRecorder (USB UVC webcam — not WebUSB)
 *
 * Deploy: config/www/gbn/
 */
class GbnPanel extends window.McPanel.Base {
  constructor() {
    super();
    this.legacyPaint = true;
    this._panel = null;
    this._players = [];
    this._selected = null;
    this._serverUrl = null;
    this._stream = null;
    this._recorder = null;
    this._chunks = [];
    this._blob = null;
    this._recordTimer = null;
    this._countdownTimer = null;
    this._captureBusy = false;
    this._cameraPermitted = false;
    this._existingPoster = null;
    this._comboOpen = false;
    this._templates = [];
    this._activeTemplateId = "";
    this._activeEventId = null;
    this._activeEventName = "";
    this._eventMedia = [];
    this._lookManuallyToggled = false;
  }

  set panel(p) {
    this._panel = p;
    this._serverUrl = this._resolveServerUrl();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._teardownCamera();
  }

  _resolveServerUrl() {
    return String(this._serverUrl || "").replace(/\/$/, "");
  }

  async _loadDirectoryUrl() {
    if (window.CoreConfigurator && this.hass) {
      this._serverUrl = await window.CoreConfigurator.getUrl(this.hass, "gbn");
    } else {
      this._serverUrl = "";
    }
  }

  async _boot() {
    await this._loadDirectoryUrl();
    await this._loadActiveEvent();
    await this._loadTemplates();
    await this._loadPlayers();
    await this._loadEventMedia();
    await this._refreshCameras();
  }

  _feedback(msg, kind = "ok") {
    const el = this.shadowRoot.getElementById("feedback");
    if (!el) return;
    el.textContent = msg;
    el.className = `feedback ${kind}`;
  }

  _errText(err) {
    if (!err) return "unknown error";
    if (typeof err === "string") return err;
    return err.message || err.error || JSON.stringify(err);
  }

  _normNeocorp(v) {
    const s = String(v || "freelancer").toLowerCase();
    return ["reboot", "helix", "endline", "freelancer"].includes(s) ? s : "freelancer";
  }

  _playerRole(player) {
    if (!player) return "neither";
    const r = String(player.mode || player.role || "").toLowerCase();
    if (r === "hunter") return "hunter";
    if (r === "bounty") return "bounty";
    if (r === "gbn" || r === "neither" || r === "other" || r === "custom") return "neither";
    if (player.hunter === 1) return "hunter";
    if (player.hunter === 2) return "neither";
    if (player.hunter === 0) return "bounty";
    return "neither";
  }

  _getRole() {
    return this._selected ? this._playerRole(this._selected) : "neither";
  }

  /** Role value sent to GBN API (hunter|bounty only). */
  _apiRole() {
    return this._getRole() === "hunter" ? "hunter" : "bounty";
  }

  async _loadTemplates() {
    try {
      const { ok, body } = await this._api("/api/poster-templates");
      this._templates = ok && Array.isArray(body) ? body : [];
    } catch (_) {
      this._templates = [];
    }
    this._fillTemplateSelect();
  }

  _fillTemplateSelect() {
    const sel = this.shadowRoot?.getElementById("fld-template");
    if (!sel) return;
    const prev = this._activeTemplateId || sel.value;
    sel.innerHTML = `<option value="">— Select template —</option>`;
    for (const t of this._templates) {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = t.builtin ? `${t.name} (built-in)` : t.name;
      sel.appendChild(opt);
    }
    if (prev && [...sel.options].some((o) => o.value === prev)) {
      sel.value = prev;
    }
  }

  _templateById(id) {
    return this._templates.find((t) => t.id === id) || null;
  }

  _readChromeFromForm() {
    const root = this.shadowRoot;
    return {
      template_id: root.getElementById("fld-template")?.value || "",
      headline: (root.getElementById("fld-headline")?.value || "").trim(),
      subtitle: (root.getElementById("fld-subtitle")?.value || "").trim(),
      amount_label: (root.getElementById("fld-amount-label")?.value || "").trim(),
      list_label: (root.getElementById("fld-list-label")?.value || "").trim(),
      list_empty: (root.getElementById("fld-list-empty")?.value || "").trim(),
    };
  }

  _applyChromeToForm(chrome) {
    const root = this.shadowRoot;
    if (!chrome) return;
    const set = (id, val) => {
      const el = root.getElementById(id);
      if (el) el.value = val ?? "";
    };
    if (chrome.template_id != null) {
      const sel = root.getElementById("fld-template");
      if (sel) sel.value = chrome.template_id;
      this._activeTemplateId = chrome.template_id || "";
    }
    set("fld-headline", chrome.headline);
    set("fld-subtitle", chrome.subtitle);
    set("fld-amount-label", chrome.amount_label);
    set("fld-list-label", chrome.list_label);
    set("fld-list-empty", chrome.list_empty);
    this._updateRoleUi();
  }

  _onTemplateSelected() {
    const id = this.shadowRoot.getElementById("fld-template")?.value || "";
    this._activeTemplateId = id;
    const tmpl = this._templateById(id);
    if (!tmpl) {
      this._updateRoleUi();
      return;
    }
    this._applyChromeToForm({
      template_id: tmpl.id,
      headline: tmpl.headline,
      subtitle: tmpl.subtitle,
      amount_label: tmpl.amount_label,
      list_label: tmpl.list_label,
      list_empty: tmpl.list_empty,
    });
  }

  _autoSelectTemplateForPlayer() {
    const role = this._getRole();
    if (role === "hunter" || role === "bounty") {
      const tmpl = this._templateById(role);
      if (tmpl) {
        this._applyChromeToForm({
          template_id: tmpl.id,
          headline: tmpl.headline,
          subtitle: tmpl.subtitle,
          amount_label: tmpl.amount_label,
          list_label: tmpl.list_label,
          list_empty: tmpl.list_empty,
        });
      } else if (role === "hunter") {
        this._applyChromeToForm({
          template_id: "hunter",
          headline: "GUN FOR HIRE",
          subtitle: "",
          amount_label: "RATE",
          list_label: "REASONS TO HIRE",
          list_empty: "Details pending",
        });
      } else {
        this._applyChromeToForm({
          template_id: "bounty",
          headline: "WANTED",
          subtitle: "DEAD OR ALIVE",
          amount_label: "REWARD",
          list_label: "WANTED FOR",
          list_empty: "Charges pending",
        });
      }
      return;
    }
    // Neither — operator must pick; clear to prompt
    this._activeTemplateId = "";
    const sel = this.shadowRoot.getElementById("fld-template");
    if (sel) sel.value = "";
    this._applyChromeToForm({
      template_id: "",
      headline: "",
      subtitle: "",
      amount_label: "",
      list_label: "",
      list_empty: "",
    });
    this._feedback("Player is neither Hunter nor Bounty — pick a poster template", "warn");
  }

  _mergeTemplateIntoList(tmpl) {
    if (!tmpl || !tmpl.id) return;
    const rest = this._templates.filter((t) => t.id !== tmpl.id);
    this._templates = [...rest, tmpl].sort((a, b) => {
      if (a.builtin !== b.builtin) return a.builtin ? -1 : 1;
      return String(a.name || "").localeCompare(String(b.name || ""));
    });
    this._activeTemplateId = tmpl.id;
    this._fillTemplateSelect();
  }

  /**
   * POST chrome as a new custom template and select it in the dropdown.
   * @returns {Promise<object|null>} created template or null
   */
  async _createTemplateFromChrome(chrome, name) {
    const headline = (chrome?.headline || "").trim();
    if (!headline) {
      this._feedback("Headline required to save a template", "warn");
      return null;
    }
    const { ok, status, body } = await this._api("/api/poster-templates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: (name || headline).trim().slice(0, 80) || "Custom poster",
        headline,
        subtitle: (chrome.subtitle || "").trim(),
        amount_label: (chrome.amount_label || "").trim() || "REWARD",
        list_label: (chrome.list_label || "").trim() || "WANTED FOR",
        list_empty: (chrome.list_empty || "").trim() || "Charges pending",
      }),
    });
    if (!ok || !body || typeof body !== "object" || !body.id) {
      const hint =
        status === 404
          ? " — GBN server is missing /api/poster-templates (deploy updated app/ to CT 101 and restart gbn)"
          : "";
      this._feedback(
        `Save template failed (${status}): ${JSON.stringify(body)}${hint}`,
        "err"
      );
      return null;
    }
    this._mergeTemplateIntoList(body);
    // Refresh from server so list matches disk; keep selection on new id
    this._activeTemplateId = body.id;
    await this._loadTemplates();
    this._applyChromeToForm({
      template_id: body.id,
      headline: body.headline,
      subtitle: body.subtitle,
      amount_label: body.amount_label,
      list_label: body.list_label,
      list_empty: body.list_empty,
    });
    return body;
  }

  async _saveTemplateAsNew() {
    const chrome = this._readChromeFromForm();
    if (!chrome.headline) {
      return this._feedback("Headline required to save a template", "warn");
    }
    const name = window.prompt(
      "Name for the new template:",
      chrome.headline.slice(0, 40) || "Custom poster"
    );
    if (!name || !name.trim()) return;
    try {
      const body = await this._createTemplateFromChrome(chrome, name.trim());
      if (body) this._feedback(`Template saved: ${body.name}`, "ok");
    } catch (err) {
      this._feedback(`Save template failed: ${this._errText(err)}`, "err");
    }
  }

  _updateLookSummary() {
    const root = this.shadowRoot;
    const summary = root?.getElementById("look-summary");
    if (!summary) return;
    const chrome = this._readChromeFromForm();
    const tmpl = this._templateById(chrome.template_id);
    const name = tmpl?.name || chrome.template_id || "none";
    const headline = chrome.headline || "—";
    summary.textContent = `Using: ${name} · ${headline}`;
  }

  _syncLookDisclosure() {
    const root = this.shadowRoot;
    const details = root?.getElementById("look-details");
    if (!details) return;
    const role = this._getRole();
    // Neither starts expanded; hunter/bounty stay collapsed unless operator opened it.
    if (role === "neither") {
      details.open = true;
    } else if (!this._lookManuallyToggled) {
      details.open = false;
    }
    this._updateLookSummary();
  }

  _updateRoleUi() {
    const root = this.shadowRoot;
    const chrome = this._readChromeFromForm();
    const role = this._getRole();
    const listLabel = chrome.list_label || (role === "hunter" ? "REASONS TO HIRE" : "WANTED FOR");
    const amountLabel = chrome.amount_label || (role === "hunter" ? "RATE" : "REWARD");
    const lbl = root.getElementById("lbl-list-field");
    const lblAmount = root.getElementById("lbl-amount-field");
    const crimes = root.getElementById("fld-crimes");
    if (lbl) {
      lbl.textContent = `${listLabel} (one per line)`;
    }
    if (lblAmount) {
      lblAmount.textContent = `${amountLabel} (₩)`;
    }
    if (crimes) {
      crimes.placeholder =
        role === "hunter"
          ? "What is your EIS?\nWhat do you want bounties to know about you?\nReviews from past clients."
          : "What are you wanted for?\nWhat are you known for?\nWhy are you dangerous?";
    }
    const hint = root.getElementById("template-hint");
    if (hint) {
      if (role === "neither") {
        hint.textContent =
          "Neither Hunter nor Bounty — select a template or edit chrome and Save as new.";
      } else {
        hint.textContent = `Auto-selected ${role} template — edit chrome and Save as new to fork.`;
      }
    }
    this._syncLookDisclosure();
  }

  _posterUrlForPlayer(playerId) {
    const base = this._resolveServerUrl();
    if (!base) return "";
    return `${base}/poster/player/${encodeURIComponent(playerId)}`;
  }

  /** Operator-facing poster link: Core Configurator URL wins over server body. */
  async _livePosterUrl(playerId, fallbackUrl = "") {
    await this._loadDirectoryUrl();
    return this._posterUrlForPlayer(playerId) || fallbackUrl || "";
  }

  async _loadPlayers() {
    if (!this.hass) return;
    try {
      const result = await this.hass.connection.sendMessagePromise({
        type: "registration/get_roster",
      });
      this._players = result.players || [];
      this._renderComboList("");
      this._feedback(`Loaded ${this._players.length} player(s)`, "ok");
    } catch (err) {
      this._players = [];
      this._renderComboList("");
      this._feedback(
        `Roster fetch failed: ${this._errText(err)} — enter name manually`,
        "warn"
      );
    }
  }

  _renderComboList(term) {
    const list = this.shadowRoot.getElementById("player-combo-list");
    if (!list) return;
    const q = (term || "").trim().toLowerCase();
    const filtered = q
      ? this._players.filter((p) => String(p.name || "").toLowerCase().includes(q))
      : this._players;
    list.innerHTML = "";
    if (!filtered.length) {
      list.innerHTML = `<div class="combo-empty">No matches</div>`;
      return;
    }
    for (const p of filtered) {
      const alleg = p.neocorp || p.allegiance || "";
      const row = document.createElement("button");
      row.type = "button";
      row.className = "combo-item";
      row.dataset.id = String(p.id);
      row.textContent = `${p.name}${alleg ? ` (${alleg})` : ""}`;
      row.onclick = () => this._selectPlayerById(String(p.id));
      list.appendChild(row);
    }
  }

  _setComboOpen(open) {
    this._comboOpen = open;
    const list = this.shadowRoot.getElementById("player-combo-list");
    if (list) list.hidden = !open;
  }

  async _selectPlayerById(id) {
    const player = this._players.find((p) => String(p.id) === id) || null;
    this._selected = player;
    this._lookManuallyToggled = false;
    this._setComboOpen(false);
    const root = this.shadowRoot;
    const input = root.getElementById("player-combo-input");
    if (!player) {
      if (input) input.value = "";
      return;
    }
    if (input) input.value = player.name || "";
    root.getElementById("fld-name").value = player.name || "";
    root.getElementById("fld-neocorp").value = this._normNeocorp(player.neocorp || player.allegiance);
    root.getElementById("fld-faction").value = player.faction || "";
    this._autoSelectTemplateForPlayer();
    await this._loadExistingPoster(String(player.id));
  }

  async _loadExistingPoster(playerId) {
    this._existingPoster = null;
    const root = this.shadowRoot;
    try {
      const { ok, status, body } = await this._api(`/api/posters/by-player/${encodeURIComponent(playerId)}`);
      if (status === 404 || !ok) {
        root.getElementById("success-box").hidden = true;
        this._feedback("No existing poster — capture or upload a new clip", "ok");
        return;
      }
      this._existingPoster = body;
      root.getElementById("fld-bounty").value = body.bounty_amount ?? "";
      root.getElementById("fld-crimes").value = (body.crimes || []).join("\n");
      root.getElementById("fld-height").value = body.stats?.height || "";
      root.getElementById("fld-weight").value = body.stats?.weight || "";
      root.getElementById("fld-age").value = body.stats?.age || "";
      root.getElementById("fld-flavor").value = body.flavor_text || "";
      if (body.faction) root.getElementById("fld-faction").value = body.faction;
      if (body.template_id || body.headline) {
        this._applyChromeToForm({
          template_id: body.template_id || "",
          headline: body.headline || "",
          subtitle: body.subtitle || "",
          amount_label: body.amount_label || "",
          list_label: body.list_label || "",
          list_empty: body.list_empty || "",
        });
      }
      // Roster wins for live NeoCorp/name/faction display
      if (this._selected) {
        root.getElementById("fld-name").value = this._selected.name || body.name || "";
        root.getElementById("fld-neocorp").value = this._normNeocorp(
          this._selected.allegiance || body.neocorp || body.allegiance
        );
        root.getElementById("fld-faction").value =
          this._selected.faction || body.faction || "";
      }
      const link = root.getElementById("poster-link");
      const url = await this._livePosterUrl(playerId, body.poster_url);
      link.href = url;
      link.textContent = url;
      root.getElementById("success-box").hidden = false;

      if (body.video_url) {
        const review = root.getElementById("review-video");
        const live = root.getElementById("live-video");
        review.src = body.video_url;
        review.classList.remove("hidden");
        live.classList.add("hidden");
        this._blob = null;
        this._setRecStatus("Existing clip loaded — retake or upload to replace");
      }
      this._feedback("Loaded existing poster for this player", "ok");
    } catch (err) {
      this._feedback(`Poster lookup failed: ${this._errText(err)}`, "warn");
    }
  }

  _token() {
    return this.hass?.auth?.data?.access_token || "";
  }

  async _api(path, options = {}) {
    const headers = Object.assign({}, options.headers || {});
    if (this._token()) headers.Authorization = `Bearer ${this._token()}`;
    const resp = await fetch(`/api/gbn/proxy${path}`, {
      ...options,
      headers,
      credentials: "same-origin",
      cache: "no-store",
    });
    const text = await resp.text();
    let body = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch (_) {
      body = text;
    }
    return { ok: resp.ok, status: resp.status, body };
  }

  async _generateFlavor() {
    const root = this.shadowRoot;
    const name = root.getElementById("fld-name").value.trim();
    const allegiance = root.getElementById("fld-neocorp").value;
    const role = this._apiRole();
    if (!name) return this._feedback("Enter a name first", "warn");
    try {
      const { ok, status, body } = await this._api("/api/flavor/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, neocorp: allegiance, role }),
      });
      if (!ok) {
        return this._feedback(`Generate failed (${status}): ${JSON.stringify(body)}`, "err");
      }
      root.getElementById("fld-bounty").value = body.bounty_amount ?? "";
      root.getElementById("fld-crimes").value = (body.crimes || []).join("\n");
      root.getElementById("fld-height").value = body.stats?.height || "";
      root.getElementById("fld-weight").value = body.stats?.weight || "";
      root.getElementById("fld-age").value = body.stats?.age || "";
      root.getElementById("fld-flavor").value = body.flavor_text || "";
      this._feedback(`Flavor generated (${body.source || "templates"})`, "ok");
    } catch (err) {
      this._feedback(`Generate failed: ${this._errText(err)}`, "err");
    }
  }

  async _loadActiveEvent() {
    // Prefer Registration WS (same source as roster); fall back to GBN proxy.
    if (this.hass) {
      try {
        const result = await this.hass.connection.sendMessagePromise({
          type: "registration/get_active_event",
        });
        this._activeEventId = result?.active_event_id || null;
        this._activeEventName = result?.event?.name || "";
        this._paintActiveEvent();
        return;
      } catch (_) {
        /* fall through */
      }
    }
    try {
      const { ok, body } = await this._api("/api/events/active");
      if (ok && body) {
        this._activeEventId = body.active_event_id || null;
        this._activeEventName = body.event_name || "";
      } else {
        this._activeEventId = null;
        this._activeEventName = "";
      }
    } catch (_) {
      this._activeEventId = null;
      this._activeEventName = "";
    }
    this._paintActiveEvent();
  }

  _paintActiveEvent() {
    const el = this.shadowRoot?.getElementById("active-event-chip");
    if (!el) return;
    if (this._activeEventId) {
      const label = this._activeEventName
        ? `${this._activeEventName} (${this._activeEventId})`
        : this._activeEventId;
      el.textContent = `Active event: ${label}`;
      el.className = "event-chip ok";
    } else {
      el.textContent = "No active event — set one in Registration before capture";
      el.className = "event-chip warn";
    }
  }

  _formatBytes(n) {
    const bytes = Number(n) || 0;
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }

  async _loadEventMedia() {
    try {
      const { ok, body } = await this._api("/api/events/media");
      this._eventMedia = ok && Array.isArray(body) ? body : [];
    } catch (_) {
      this._eventMedia = [];
    }
    this._paintEventMedia();
  }

  _paintEventMedia() {
    const body = this.shadowRoot?.getElementById("event-media-body");
    if (!body) return;
    if (!this._eventMedia.length) {
      body.innerHTML = `<tr><td colspan="4" class="muted">No event media folders yet</td></tr>`;
      return;
    }
    body.innerHTML = "";
    for (const row of this._eventMedia) {
      const tr = document.createElement("tr");
      if (row.is_active) tr.className = "is-active";
      const name = row.event_name
        ? `${row.event_name}`
        : row.is_active
          ? "(active)"
          : "";
      tr.innerHTML = `
        <td><code>${row.event_id}</code>${name ? `<div class="muted">${name}</div>` : ""}${
          row.is_active ? `<div class="badge">active</div>` : ""
        }</td>
        <td>${row.clip_count}</td>
        <td>${this._formatBytes(row.bytes_total)}</td>
        <td class="actions-cell"></td>
      `;
      const actions = tr.querySelector(".actions-cell");
      const btnExport = document.createElement("button");
      btnExport.type = "button";
      btnExport.textContent = "Export clips";
      btnExport.onclick = () => this._exportEventClips(row.event_id);
      const btnDel = document.createElement("button");
      btnDel.type = "button";
      btnDel.className = "danger";
      btnDel.textContent = "Delete";
      btnDel.onclick = () => this._deleteEventMedia(row.event_id);
      actions.appendChild(btnExport);
      actions.appendChild(btnDel);
      body.appendChild(tr);
    }
  }

  async _exportEventClips(eventId) {
    if (!eventId) return;
    try {
      this._feedback(`Exporting clips for ${eventId}…`, "ok");
      const headers = {};
      if (this._token()) headers.Authorization = `Bearer ${this._token()}`;
      const resp = await fetch(
        `/api/gbn/proxy/api/events/${encodeURIComponent(eventId)}/clips/export`,
        { headers, credentials: "same-origin", cache: "no-store" }
      );
      if (!resp.ok) {
        const text = await resp.text();
        return this._feedback(`Export failed (${resp.status}): ${text}`, "err");
      }
      const blob = await resp.blob();
      const cd = resp.headers.get("Content-Disposition") || "";
      const match = /filename="?([^";]+)"?/i.exec(cd);
      const filename = match?.[1] || `gbn-clips-${eventId}.zip`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      this._feedback(`Downloaded ${filename}`, "ok");
    } catch (err) {
      this._feedback(`Export failed: ${this._errText(err)}`, "err");
    }
  }

  async _deleteEventMedia(eventId) {
    if (!eventId) return;
    const ok = window.confirm(
      `Delete all clips and posters for event “${eventId}”? This cannot be undone.`
    );
    if (!ok) return;
    try {
      const { ok: success, status, body } = await this._api(
        `/api/events/${encodeURIComponent(eventId)}/media`,
        { method: "DELETE" }
      );
      if (!success) {
        return this._feedback(
          `Delete failed (${status}): ${JSON.stringify(body)}`,
          "err"
        );
      }
      this._feedback(`Deleted media for ${eventId}`, "ok");
      await this._loadEventMedia();
    } catch (err) {
      this._feedback(`Delete failed: ${this._errText(err)}`, "err");
    }
  }

  _setRecStatus(text) {
    const el = this.shadowRoot.getElementById("rec-status");
    if (el) el.textContent = text || "";
  }

  _clearCaptureTimers() {
    if (this._recordTimer) {
      clearTimeout(this._recordTimer);
      this._recordTimer = null;
    }
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer);
      this._countdownTimer = null;
    }
  }

  _teardownCamera() {
    this._clearCaptureTimers();
    this._captureBusy = false;
    if (this._recorder && this._recorder.state !== "inactive") {
      try {
        this._recorder.stop();
      } catch (_) {}
    }
    this._recorder = null;
    if (this._stream) {
      this._stream.getTracks().forEach((t) => t.stop());
      this._stream = null;
    }
    const live = this.shadowRoot?.getElementById("live-video");
    if (live) live.srcObject = null;
  }

  _mediaDevices() {
    return (
      navigator.mediaDevices ||
      window.navigator?.mediaDevices ||
      window.top?.navigator?.mediaDevices ||
      null
    );
  }

  _cameraBlockedReason() {
    const origin = window.location.origin || "(unknown)";
    const md = this._mediaDevices();
    // Only hard-block when the API is missing. Insecure HTTP can still work for
    // this session (Zen/Firefox prefs or Chrome insecure-origin flag).
    if (!md?.getUserMedia) {
      return (
        `Camera API unavailable at ${origin}. ` +
        `Browsers hide getUserMedia on plain HTTP. ` +
        `Zen/Firefox: about:config → set media.devices.insecure.enabled and ` +
        `media.getusermedia.insecure.enabled to true, then restart the browser. ` +
        `Chrome/Edge: chrome://flags/#unsafely-treat-insecure-origin-as-secure ` +
        `→ add ${origin} → Relaunch. HTTPS is required for “Remember” to stick.`
      );
    }
    return null;
  }

  _cameraHttpHint() {
    if (window.isSecureContext) return null;
    return (
      "HTTP session: camera can work after Allow, but browsers will not Remember " +
      "permission until HA is on HTTPS."
    );
  }

  async _refreshCameras() {
    const sel = this.shadowRoot.getElementById("camera-select");
    const blocked = this._cameraBlockedReason();
    if (blocked) {
      this._feedback(blocked, "err");
      return;
    }
    const md = this._mediaDevices();
    if (!sel || !md?.enumerateDevices) {
      this._feedback("Camera API unavailable in this browser", "err");
      return;
    }
    // Do not call getUserMedia here — that causes a second permission prompt.
    // After Start camera once, labels usually populate.
    try {
      const devices = await md.enumerateDevices();
      const cams = devices.filter((d) => d.kind === "videoinput");
      const prev = sel.value;
      sel.innerHTML = "";
      if (!cams.length) {
        sel.innerHTML = `<option value="">No cameras found — Start camera first</option>`;
        return;
      }
      cams.forEach((d, i) => {
        const opt = document.createElement("option");
        opt.value = d.deviceId;
        opt.textContent = d.label || `Camera ${i + 1}`;
        sel.appendChild(opt);
      });
      if (prev) sel.value = prev;
      if (!this._cameraPermitted) {
        const hint = this._cameraHttpHint();
        this._feedback(
          hint
            ? `Camera list loaded — Start camera to grant access. ${hint}`
            : "Camera list loaded — Start camera if needed",
          "ok"
        );
      }
    } catch (err) {
      this._feedback(`Camera list failed: ${this._errText(err)}`, "err");
    }
  }

  async _startCamera() {
    const blocked = this._cameraBlockedReason();
    if (blocked) {
      this._feedback(blocked, "err");
      return;
    }
    const md = this._mediaDevices();
    this._teardownCamera();
    const deviceId = this.shadowRoot.getElementById("camera-select").value;
    const constraints = {
      audio: false,
      video: deviceId
        ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
        : { width: { ideal: 1280 }, height: { ideal: 720 } },
    };
    try {
      this._stream = await md.getUserMedia(constraints);
      this._cameraPermitted = true;
      const live = this.shadowRoot.getElementById("live-video");
      const review = this.shadowRoot.getElementById("review-video");
      live.srcObject = this._stream;
      live.classList.remove("hidden");
      review.classList.add("hidden");
      this._blob = null;
      const hint = this._cameraHttpHint();
      this._feedback(hint ? `Camera live. ${hint}` : "Camera live", "ok");
      this._setRecStatus("Ready");
      await this._refreshCameras();
    } catch (err) {
      const hint = this._cameraHttpHint();
      this._feedback(
        `Camera failed: ${this._errText(err)}${hint ? ` — ${hint}` : ""}`,
        "err"
      );
    }
  }

  _pickMime() {
    const candidates = [
      "video/webm;codecs=vp9",
      "video/webm;codecs=vp8",
      "video/webm",
    ];
    for (const m of candidates) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported(m)) return m;
    }
    return "";
  }

  async _recordClip() {
    if (this._captureBusy) {
      return this._feedback("Already recording", "warn");
    }
    if (!this._stream) {
      await this._startCamera();
      if (!this._stream) return;
    }

    // Kill any leftover countdown/stop timers so a double-click cannot
    // leave an interval that re-starts MediaRecorder every second.
    this._clearCaptureTimers();
    if (this._recorder && this._recorder.state !== "inactive") {
      try {
        this._recorder.stop();
      } catch (_) {}
    }

    let secs = Number(this.shadowRoot.getElementById("fld-seconds").value) || 4;
    secs = Math.min(5, Math.max(3, secs));
    this._chunks = [];
    this._blob = null;
    this._captureBusy = true;

    const mime = this._pickMime();
    let recorder;
    try {
      recorder = mime
        ? new MediaRecorder(this._stream, { mimeType: mime })
        : new MediaRecorder(this._stream);
    } catch (err) {
      this._captureBusy = false;
      return this._feedback(`MediaRecorder failed: ${this._errText(err)}`, "err");
    }
    this._recorder = recorder;

    recorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size) this._chunks.push(ev.data);
    };
    recorder.onstop = () => {
      this._clearCaptureTimers();
      this._captureBusy = false;
      if (this._recorder !== recorder) return;
      this._blob = new Blob(this._chunks, {
        type: recorder.mimeType || "video/webm",
      });
      const review = this.shadowRoot.getElementById("review-video");
      const live = this.shadowRoot.getElementById("live-video");
      if (review.src && review.src.startsWith("blob:")) URL.revokeObjectURL(review.src);
      review.src = URL.createObjectURL(this._blob);
      review.classList.remove("hidden");
      live.classList.add("hidden");
      review.play?.().catch(() => {});
      this._setRecStatus(`Captured ${(this._blob.size / 1024).toFixed(0)} KB`);
      this._feedback("Clip ready — review, retake, or create poster", "ok");
    };

    let left = 3;
    let started = false;
    this._setRecStatus(`Recording in ${left}…`);
    const countdown = setInterval(() => {
      if (this._countdownTimer !== countdown) {
        clearInterval(countdown);
        return;
      }
      left -= 1;
      if (left > 0) {
        this._setRecStatus(`Recording in ${left}…`);
        return;
      }
      clearInterval(countdown);
      if (this._countdownTimer === countdown) this._countdownTimer = null;
      if (started || this._recorder !== recorder) return;
      started = true;
      try {
        recorder.start(200);
      } catch (err) {
        this._captureBusy = false;
        this._feedback(`Record failed: ${this._errText(err)}`, "err");
        return;
      }
      this._setRecStatus(`Recording ${secs}s…`);
      const stopTimer = setTimeout(() => {
        if (this._recordTimer === stopTimer) this._recordTimer = null;
        if (this._recorder === recorder && recorder.state === "recording") {
          try {
            recorder.stop();
          } catch (_) {}
        }
      }, secs * 1000);
      this._recordTimer = stopTimer;
    }, 1000);
    this._countdownTimer = countdown;
  }

  _retake() {
    this._clearCaptureTimers();
    this._captureBusy = false;
    const review = this.shadowRoot.getElementById("review-video");
    if (review.src && review.src.startsWith("blob:")) URL.revokeObjectURL(review.src);
    review.removeAttribute("src");
    review.classList.add("hidden");
    this._blob = null;
    this._chunks = [];
    const upload = this.shadowRoot.getElementById("fld-upload");
    if (upload) upload.value = "";
    this._startCamera();
  }

  _onUpload(ev) {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    this._blob = file;
    const review = this.shadowRoot.getElementById("review-video");
    const live = this.shadowRoot.getElementById("live-video");
    if (review.src && review.src.startsWith("blob:")) URL.revokeObjectURL(review.src);
    review.src = URL.createObjectURL(file);
    review.classList.remove("hidden");
    live.classList.add("hidden");
    this._setRecStatus(`Upload ready: ${file.name} (${(file.size / 1024).toFixed(0)} KB)`);
    this._feedback("Upload loaded — create poster to save", "ok");
  }

  async _submit() {
    const root = this.shadowRoot;
    const name = root.getElementById("fld-name").value.trim();
    const allegiance = root.getElementById("fld-neocorp").value;
    const faction = root.getElementById("fld-faction").value.trim();
    if (!name) return this._feedback("Name required", "warn");
    if (!this._blob) return this._feedback("Record or upload a clip first", "warn");

    const crimes = root
      .getElementById("fld-crimes")
      .value.split(/\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    const stats = {
      height: root.getElementById("fld-height").value.trim() || "5'10\"",
      weight: root.getElementById("fld-weight").value.trim() || "165 LBS",
      age: root.getElementById("fld-age").value.trim() || "29",
    };
    const bounty = Number(root.getElementById("fld-bounty").value) || 1000000;
    const flavor = root.getElementById("fld-flavor").value.trim();
    const playerId = this._selected?.id != null ? String(this._selected.id) : "";
    if (!playerId) return this._feedback("Select a player from the roster first", "warn");
    if (!this._activeEventId) {
      await this._loadActiveEvent();
      if (!this._activeEventId) {
        return this._feedback(
          "No active event — set one in Registration before creating a poster",
          "warn"
        );
      }
    }
    const role = this._apiRole();
    const chrome = this._readChromeFromForm();
    const selectedTmpl = this._templateById(chrome.template_id);
    if (this._getRole() === "neither") {
      if (!chrome.template_id || !selectedTmpl) {
        return this._feedback(
          "Select a poster template, or Save as new template before Create",
          "warn"
        );
      }
    } else if (!chrome.template_id && !chrome.headline) {
      return this._feedback("Select a poster template (or set a headline) first", "warn");
    }

    const form = new FormData();
    form.append("name", name);
    form.append("neocorp", allegiance);
    form.append("allegiance", allegiance); // legacy alias accepted by server
    form.append("faction", faction);
    form.append("role", role);
    form.append("player_id", playerId);
    form.append("bounty_amount", String(bounty));
    form.append("crimes", JSON.stringify(crimes));
    form.append("stats", JSON.stringify(stats));
    form.append("flavor_text", flavor);
    form.append("template_id", chrome.template_id);
    form.append("headline", chrome.headline);
    form.append("subtitle", chrome.subtitle);
    form.append("amount_label", chrome.amount_label);
    form.append("list_label", chrome.list_label);
    form.append("list_empty", chrome.list_empty);
    const safe = name.replace(/\s+/g, "_").toLowerCase();
    const filename =
      this._blob instanceof File && this._blob.name
        ? this._blob.name
        : `${safe}.webm`;
    form.append("video", this._blob, filename);

    try {
      this._feedback("Uploading poster…", "ok");
      const headers = {};
      if (this._token()) headers.Authorization = `Bearer ${this._token()}`;
      const resp = await fetch(`/api/gbn/proxy/api/posters`, {
        method: "POST",
        headers,
        body: form,
        credentials: "same-origin",
        cache: "no-store",
      });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        return this._feedback(`Upload failed (${resp.status}): ${JSON.stringify(body)}`, "err");
      }
      this._existingPoster = body;
      const link = root.getElementById("poster-link");
      const url = await this._livePosterUrl(playerId, body.poster_url);
      link.href = url;
      link.textContent = url;
      root.getElementById("success-box").hidden = false;
      this._feedback(`Poster saved for player ${playerId}`, "ok");
      await this._loadEventMedia();
    } catch (err) {
      this._feedback(`Upload failed: ${this._errText(err)}`, "err");
    }
  }

  async _saveServerUrl() {
    const inp = this.shadowRoot.getElementById("server-url-input");
    const url = (inp?.value || "").trim().replace(/\/$/, "");
    if (!url) return;
    try {
      if (window.CoreConfigurator) {
        await window.CoreConfigurator.setService(this.hass, "gbn", { url });
      } else {
        await this.hass.connection.sendMessagePromise({
          type: "core_configurator/set_service",
          key: "gbn",
          url,
        });
      }
      this._serverUrl = url;
      this.shadowRoot.getElementById("server-url-dialog").style.display = "none";
      this._feedback(`GBN server saved in Core Configurator: ${url}`, "ok");
    } catch (err) {
      this._feedback(`Save failed: ${this._errText(err)}`, "err");
    }
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block; height: 100%; overflow: auto;
          background: var(--primary-background-color);
          color: var(--primary-text-color);
        }
        .wrap { max-width: 1200px; margin: 0 auto; padding: 1rem 1.25rem 2rem; }
        .page-header {
          display: flex; justify-content: space-between; align-items: center;
          padding-bottom: 0.75rem; margin-bottom: 1rem;
        }
        .page-header h1 { margin: 0; font-size: 1.25rem; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
        .card {
          background: var(--card-background-color, #111);
          border: 1px solid var(--divider-color, #1f3a44);
          border-radius: 4px; padding: 1rem;
        }
        .card h2 {
          margin: 0 0 0.75rem; font-size: 0.95rem;
          letter-spacing: 0.12em; text-transform: uppercase;
          color: var(--ac-cyan, #00e5ff);
        }
        label {
          display: block; font-size: 0.7rem; letter-spacing: 0.1em;
          margin: 0.55rem 0 0.2rem; opacity: 0.75;
        }
        input, select, textarea, button {
          font: inherit; width: 100%; box-sizing: border-box;
          background: rgba(0,0,0,0.35); color: inherit;
          border: 1px solid var(--divider-color, #1f3a44);
          border-radius: 3px; padding: 0.45rem 0.55rem;
        }
        textarea { min-height: 5.5rem; resize: vertical; }
        .row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.5rem; }
        .actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.75rem; }
        .actions button { width: auto; cursor: pointer; }
        button.primary { border-color: var(--ac-cyan, #00e5ff); color: var(--ac-cyan, #00e5ff); }
        button.danger { border-color: #ff4d5a; color: #ff4d5a; }
        .preview {
          position: relative; background: #000; aspect-ratio: 16/9;
          border: 1px solid var(--divider-color, #1f3a44); overflow: hidden;
          margin-top: 0.75rem;
        }
        .preview video { width: 100%; height: 100%; object-fit: cover; display: block; }
        .preview video.hidden { display: none; }
        .rec-status {
          margin-top: 0.4rem; font-size: 0.8rem; min-height: 1.2em;
          color: var(--ac-cyan, #00e5ff);
        }
        .feedback { margin-top: 0.75rem; font-size: 0.85rem; min-height: 1.2em; }
        .feedback.ok { color: #6dffb0; }
        .feedback.warn { color: #ffd166; }
        .feedback.err { color: #ff6b7a; }
        #success-box {
          margin-top: 0.75rem; padding: 0.75rem;
          border: 1px solid var(--ac-cyan, #00e5ff);
        }
        #success-box a { color: var(--ac-cyan, #00e5ff); word-break: break-all; }
        .dialog {
          display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.55);
          align-items: center; justify-content: center; z-index: 20;
        }
        .dialog-inner {
          background: var(--card-background-color, #111); padding: 1rem;
          width: min(420px, 90vw); border: 1px solid var(--divider-color);
        }
        .hint { font-size: 0.7rem; opacity: 0.65; margin-top: 0.35rem; }
        .event-chip {
          font-size: 0.8rem; margin: 0 0 0.75rem; padding: 0.4rem 0.6rem;
          border: 1px solid var(--divider-color, #1f3a44); border-radius: 3px;
        }
        .event-chip.ok { border-color: #6dffb0; color: #6dffb0; }
        .event-chip.warn { border-color: #ffd166; color: #ffd166; }
        details.look {
          margin-bottom: 0.75rem;
          border: 1px solid var(--divider-color, #1f3a44);
          border-radius: 3px; padding: 0.35rem 0.55rem 0.55rem;
        }
        details.look > summary {
          cursor: pointer; list-style: none;
          font-size: 0.8rem; letter-spacing: 0.08em; text-transform: uppercase;
          color: var(--ac-cyan, #00e5ff); padding: 0.35rem 0;
        }
        details.look > summary::-webkit-details-marker { display: none; }
        #look-summary { font-size: 0.75rem; opacity: 0.75; margin: 0 0 0.35rem; }
        .media-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
        .media-table th, .media-table td {
          text-align: left; padding: 0.4rem 0.35rem;
          border-bottom: 1px solid var(--divider-color, #1f3a44);
          vertical-align: top;
        }
        .media-table tr.is-active { background: rgba(0, 229, 255, 0.06); }
        .media-table .actions-cell { display: flex; flex-wrap: wrap; gap: 0.35rem; }
        .media-table .actions-cell button { width: auto; }
        .media-table .muted { opacity: 0.65; font-size: 0.75rem; }
        .media-table .badge {
          display: inline-block; margin-top: 0.2rem; font-size: 0.65rem;
          letter-spacing: 0.08em; text-transform: uppercase; color: var(--ac-cyan, #00e5ff);
        }
        .cam-row {
          display: grid;
          grid-template-columns: 2fr 1fr auto auto;
          gap: 0.5rem;
          align-items: end;
        }
        @media (max-width: 700px) {
          .cam-row { grid-template-columns: 1fr 1fr; }
        }
        .combo { position: relative; }
        .combo-list {
          position: absolute; left: 0; right: 0; top: 100%; z-index: 5;
          max-height: 220px; overflow: auto;
          background: var(--card-background-color, #111);
          border: 1px solid var(--divider-color, #1f3a44);
        }
        .combo-item {
          display: block; width: 100%; text-align: left; cursor: pointer;
          border: 0; border-bottom: 1px solid var(--divider-color, #1f3a44);
          border-radius: 0; background: transparent;
        }
        .combo-item:hover { background: rgba(0, 229, 255, 0.08); }
        .combo-empty { padding: 0.5rem; opacity: 0.6; font-size: 0.8rem; }
        .upload-row { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
        .upload-row input[type=file] { flex: 1; min-width: 180px; }
      </style>
      <div class="wrap">
        <header class="page-header">
          <h1>Galactic Bounty Network</h1>
          <div class="actions">
            <button type="button" id="btn-reload">Reload roster</button>
            <button type="button" id="btn-server">Server URL</button>
          </div>
        </header>
        <div id="active-event-chip" class="event-chip warn">Loading active event…</div>

        <div class="grid">
          <section class="card">
            <h2>Subject</h2>
            <label for="player-combo-input">Registration roster</label>
            <div class="combo">
              <input id="player-combo-input" autocomplete="off" placeholder="Type a name or open the list…" />
              <div id="player-combo-list" class="combo-list" hidden></div>
            </div>
            <label for="fld-name">Name</label>
            <input id="fld-name" autocomplete="off" />
            <label for="fld-neocorp">Allegiance/NeoCorp</label>
            <select id="fld-neocorp">
              <option value="reboot">reboot</option>
              <option value="helix">helix</option>
              <option value="endline">endline</option>
              <option value="freelancer" selected>freelancer</option>
            </select>
            <label for="fld-faction">Faction</label>
            <input id="fld-faction" autocomplete="off" />
          </section>

          <section class="card">
            <h2>Poster copy</h2>
            <p id="look-summary">Using: —</p>
            <details class="look" id="look-details">
              <summary>Customize poster look</summary>
              <label for="fld-template">Poster template</label>
              <select id="fld-template">
                <option value="">— Select template —</option>
              </select>
              <p class="hint" id="template-hint">Hunter/Bounty auto-select; other roles pick a template.</p>
              <div class="row">
                <div>
                  <label for="fld-headline">Headline title</label>
                  <input id="fld-headline" placeholder="WANTED / GUN FOR HIRE / …" />
                </div>
                <div>
                  <label for="fld-subtitle">Subtitle (optional)</label>
                  <input id="fld-subtitle" placeholder="DEAD OR ALIVE" />
                </div>
              </div>
              <div class="row">
                <div>
                  <label for="fld-amount-label">Amount label</label>
                  <input id="fld-amount-label" placeholder="REWARD / RATE" />
                </div>
                <div>
                  <label for="fld-list-label">List label</label>
                  <input id="fld-list-label" placeholder="WANTED FOR / REASONS TO HIRE" />
                </div>
              </div>
              <label for="fld-list-empty">Empty-list placeholder</label>
              <input id="fld-list-empty" placeholder="Charges pending" />
              <div class="actions" style="margin-top:0.5rem">
                <button type="button" id="btn-template-save">Save as new template</button>
              </div>
              <p class="hint">Required before Create if you changed chrome for a non-Hunter/Bounty player.</p>
            </details>
            <label id="lbl-amount-field" for="fld-bounty">REWARD (₩)</label>
            <input id="fld-bounty" type="number" min="0" step="10000" value="1000000" />
            <label id="lbl-list-field" for="fld-crimes">WANTED FOR (one per line)</label>
            <textarea id="fld-crimes"></textarea>
            <div class="row">
              <div>
                <label for="fld-height">Height</label>
                <input id="fld-height" />
              </div>
              <div>
                <label for="fld-weight">Weight</label>
                <input id="fld-weight" />
              </div>
              <div>
                <label for="fld-age">Age</label>
                <input id="fld-age" />
              </div>
            </div>
            <label for="fld-flavor">Flavor text</label>
            <textarea id="fld-flavor"></textarea>
            <div class="actions">
              <button type="button" class="primary" id="btn-generate">Generate</button>
            </div>
            <p class="hint">Templates now; later this can poll the on-site AI model.</p>
          </section>

          <section class="card" style="grid-column: 1 / -1">
            <h2>Capture (3–5s)</h2>
            <div class="cam-row">
              <div>
                <label for="camera-select">Camera</label>
                <select id="camera-select"></select>
              </div>
              <div>
                <label for="fld-seconds">Seconds</label>
                <input id="fld-seconds" type="number" min="3" max="5" value="4" />
              </div>
              <button type="button" id="btn-cam-refresh">Refresh cams</button>
              <button type="button" id="btn-cam-start">Start camera</button>
            </div>
            <div class="preview">
              <video id="live-video" autoplay muted playsinline></video>
              <video id="review-video" class="hidden" controls playsinline></video>
            </div>
            <div class="rec-status" id="rec-status"></div>
            <div class="actions">
              <button type="button" class="danger" id="btn-record">Record</button>
              <button type="button" id="btn-retake">Retake</button>
              <label class="upload-row" style="width:auto;margin:0">
                <input type="file" id="fld-upload" accept="video/*" />
              </label>
              <button type="button" class="primary" id="btn-submit">Create poster</button>
            </div>
            <p class="hint">Upload a video file instead of recording. Retake clears upload and returns to camera.</p>
            <div id="success-box" hidden>
              <strong>Poster live</strong>
              <div><a id="poster-link" href="#" target="_blank" rel="noopener"></a></div>
            </div>
          </section>

          <section class="card" style="grid-column: 1 / -1">
            <h2>Event media</h2>
            <div class="actions" style="margin-top:0">
              <button type="button" id="btn-media-refresh">Refresh</button>
            </div>
            <p class="hint">Clips are stored per event as {player_id}.ext. Export downloads a zip of videos only.</p>
            <table class="media-table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Clips</th>
                  <th>Size</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody id="event-media-body">
                <tr><td colspan="4" class="muted">Loading…</td></tr>
              </tbody>
            </table>
          </section>
        </div>

        <div class="feedback" id="feedback"></div>
      </div>

      <div class="dialog" id="server-url-dialog">
        <div class="dialog-inner">
          <h2 style="margin-top:0">Bounty server URL</h2>
          <input id="server-url-input" />
          <div class="actions">
            <button type="button" class="primary" id="btn-server-save">Save</button>
            <button type="button" id="btn-server-cancel">Cancel</button>
          </div>
        </div>
      </div>
    `;

    const root = this.shadowRoot;
    root.getElementById("btn-reload").onclick = async () => {
      await this._loadActiveEvent();
      await this._loadPlayers();
      await this._loadEventMedia();
    };
    root.getElementById("btn-generate").onclick = () => this._generateFlavor();
    root.getElementById("btn-cam-refresh").onclick = () => this._refreshCameras();
    root.getElementById("btn-cam-start").onclick = () => this._startCamera();
    root.getElementById("btn-record").onclick = () => this._recordClip();
    root.getElementById("btn-retake").onclick = () => this._retake();
    root.getElementById("btn-submit").onclick = () => this._submit();
    root.getElementById("btn-media-refresh").onclick = async () => {
      await this._loadActiveEvent();
      await this._loadEventMedia();
    };
    root.getElementById("fld-upload").onchange = (ev) => this._onUpload(ev);
    root.getElementById("fld-template").onchange = () => {
      this._onTemplateSelected();
      this._updateLookSummary();
    };
    root.getElementById("btn-template-save").onclick = () => this._saveTemplateAsNew();
    const lookDetails = root.getElementById("look-details");
    if (lookDetails) {
      lookDetails.addEventListener("toggle", () => {
        this._lookManuallyToggled = true;
      });
    }
    for (const id of [
      "fld-headline",
      "fld-subtitle",
      "fld-amount-label",
      "fld-list-label",
      "fld-list-empty",
    ]) {
      root.getElementById(id).oninput = () => this._updateRoleUi();
    }
    this._fillTemplateSelect();
    this._paintActiveEvent();
    this._paintEventMedia();

    const combo = root.getElementById("player-combo-input");
    combo.onfocus = () => {
      this._renderComboList(combo.value);
      this._setComboOpen(true);
    };
    combo.oninput = () => {
      this._renderComboList(combo.value);
      this._setComboOpen(true);
    };
    combo.onkeydown = (ev) => {
      if (ev.key === "Escape") this._setComboOpen(false);
      if (ev.key === "ArrowDown") {
        this._renderComboList(combo.value);
        this._setComboOpen(true);
      }
    };
    root.addEventListener("click", (ev) => {
      const path = ev.composedPath();
      if (!path.includes(combo) && !path.includes(root.getElementById("player-combo-list"))) {
        this._setComboOpen(false);
      }
    });

    root.getElementById("btn-server").onclick = () => {
      root.getElementById("server-url-input").value = this._serverUrl || "";
      root.getElementById("server-url-dialog").style.display = "flex";
    };
    root.getElementById("btn-server-save").onclick = () => this._saveServerUrl();
    root.getElementById("btn-server-cancel").onclick = () => {
      root.getElementById("server-url-dialog").style.display = "none";
    };
    this._updateRoleUi();
  }
}

customElements.define("gbn-panel", GbnPanel);
