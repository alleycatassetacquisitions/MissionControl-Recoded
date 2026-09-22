/**
 * Mission Control shared panel kit.
 *
 * Loaded via extra_module_url before any feature panel:
 *
 *   panel_custom:
 *     - name: my-panel
 *       ...
 *       js_url: /local/my_app/my-panel.js
 *       config:
 *         extra_module_url:
 *           - /local/shared_libraries/mc-panel.js
 *
 * What this module provides
 * -------------------------
 * 1. CSS custom properties injected into :root — design tokens shared by
 *    every Mission Control panel so they all look the same without copying
 *    colour values into each panel.
 *
 * 2. McPanelBase — a base class for Mission Control Web Components.
 *    Panels extend it and get:
 *      - _hass getter / setter with lazy init guard
 *      - _esc(str) — HTML-escape helper
 *      - _feedback(msg, kind) — show "ok" / "err" / "warn" messages
 *      - _clearFeedback() — immediately clear the feedback element
 *    Panels still call this.attachShadow({mode:"open"}) and define
 *    their own _render() / _boot() / _paint() methods.
 *
 * 3. window.McPanel — the exported namespace:
 *      window.McPanel.Base   — McPanelBase class
 *      window.McPanel.tokens — the raw token object (for dynamic use)
 *
 * Usage in a feature panel
 * -------------------------
 *   class MyPanel extends window.McPanel.Base {
 *     constructor() {
 *       super();
 *       this.attachShadow({ mode: "open" });
 *     }
 *     set hass(hass) {
 *       super.hass = hass; // triggers lazy init
 *     }
 *     get hass() { return super.hass; }
 *     _render() { this.shadowRoot.innerHTML = `<style>${window.McPanel.Base.sharedStyles()}</style>…`; }
 *     async _boot() { … }
 *   }
 *   customElements.define("my-panel", MyPanel);
 */

(function attachMcPanel(global) {
  "use strict";

  // -------------------------------------------------------------------------
  // 1. Design tokens
  // -------------------------------------------------------------------------

  const tokens = {
    // Backgrounds
    bgPrimary:    "var(--primary-background-color, #0b1020)",
    bgCard:       "var(--card-background-color, #12192e)",
    bgSecondary:  "var(--secondary-background-color, #0d1426)",

    // Text
    textPrimary:   "var(--primary-text-color, #e8eefc)",
    textSecondary: "var(--secondary-text-color, #9aa8c7)",

    // Accent
    accent:        "var(--primary-color, #00e5ff)",

    // Borders
    borderSubtle:  "rgba(255,255,255,0.08)",
    borderInput:   "rgba(255,255,255,0.12)",

    // Status colours
    colorOk:       "#7dffb3",
    colorErr:      "#ff6b8a",
    colorWarn:     "#ffd770",

    // Radius / spacing
    radiusCard:   "10px",
    radiusInput:  "6px",
    radiusBtn:    "6px",
    gapCard:      "14px",
    padCard:      "16px",
  };

  // Inject CSS custom properties into :root once.
  if (!global.__mcPanelTokensInjected) {
    const style = document.createElement("style");
    style.textContent = `:root {
  --mc-bg-primary:    ${tokens.bgPrimary};
  --mc-bg-card:       ${tokens.bgCard};
  --mc-bg-secondary:  ${tokens.bgSecondary};
  --mc-text-primary:  ${tokens.textPrimary};
  --mc-text-secondary:${tokens.textSecondary};
  --mc-accent:        ${tokens.accent};
  --mc-border-subtle: ${tokens.borderSubtle};
  --mc-border-input:  ${tokens.borderInput};
  --mc-color-ok:      ${tokens.colorOk};
  --mc-color-err:     ${tokens.colorErr};
  --mc-color-warn:    ${tokens.colorWarn};
  --mc-radius-card:   ${tokens.radiusCard};
  --mc-radius-input:  ${tokens.radiusInput};
  --mc-radius-btn:    ${tokens.radiusBtn};
  --mc-gap-card:      ${tokens.gapCard};
  --mc-pad-card:      ${tokens.padCard};
}`;
    document.head.appendChild(style);
    global.__mcPanelTokensInjected = true;
  }

  // -------------------------------------------------------------------------
  // 2. McPanelBase
  // -------------------------------------------------------------------------

  class McPanelBase extends HTMLElement {
    constructor() {
      super();
      this._hass = null;
      this._initialized = false;
      this._fbTimer = null;
    }

    // -- hass lifecycle -------------------------------------------------------

    /** Called by HA whenever the hass object is updated. */
    set hass(hass) {
      this._hass = hass;
      if (!this._initialized) {
        this._initialized = true;
        if (typeof this._render === "function") this._render();
        if (typeof this._boot  === "function") this._boot();
      }
    }

    get hass() {
      return this._hass;
    }

    connectedCallback() {
      if (this._hass && !this._initialized) {
        this._initialized = true;
        if (typeof this._render === "function") this._render();
        if (typeof this._boot  === "function") this._boot();
      }
    }

    disconnectedCallback() {
      this._initialized = false;
      clearTimeout(this._fbTimer);
    }

    // -- utilities ------------------------------------------------------------

    /**
     * HTML-escape a value for safe insertion into innerHTML.
     * @param {*} s
     * @returns {string}
     */
    _esc(s) {
      return String(s ?? "").replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;",
        '"': "&quot;", "'": "&#39;",
      })[c]);
    }

    /**
     * Show a feedback message in the element with id="feedback".
     * kind is "ok" (auto-clears after 3 s), "err", or "warn".
     * @param {string} msg
     * @param {"ok"|"err"|"warn"} kind
     */
    _feedback(msg, kind = "ok") {
      const root = this.shadowRoot || this;
      const el = root.getElementById("feedback");
      if (!el) return;
      clearTimeout(this._fbTimer);
      el.textContent = msg;
      el.className = `feedback ${kind}`;
      if (kind === "ok") {
        this._fbTimer = setTimeout(() => {
          el.textContent = "";
          el.className = "feedback";
        }, 3000);
      }
    }

    /** Immediately clear the feedback element. */
    _clearFeedback() {
      const root = this.shadowRoot || this;
      const el = root.getElementById("feedback");
      if (!el) return;
      clearTimeout(this._fbTimer);
      el.textContent = "";
      el.className = "feedback";
    }

    // -- shared styles -------------------------------------------------------

    /**
     * Returns a CSS string (without <style> tags) that panels should include
     * in their shadow DOM styles.  Covers typography, card, input, button,
     * and feedback primitives.
     * @returns {string}
     */
    static sharedStyles() {
      return `
        :host {
          display: block;
          height: 100%;
          overflow: auto;
          background: var(--mc-bg-primary);
          color: var(--mc-text-primary);
          font-family: var(--primary-font-family, system-ui, sans-serif);
        }
        .wrap { max-width: 980px; margin: 0 auto; padding: 1rem 1.25rem 3rem; }

        /* Page header */
        .page-header {
          display: flex; align-items: flex-end; gap: 16px;
          padding-bottom: 12px; margin-bottom: 20px;
          border-bottom: 1px solid var(--mc-border-subtle);
        }
        .page-header h1 { margin: 0; font-size: 20px; font-weight: 600; }
        .sub { margin: 4px 0 0; font-size: 13px; color: var(--mc-text-secondary); }
        .header-actions { margin-left: auto; display: flex; align-items: center; gap: 12px; }

        /* Cards grid */
        .cards {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
          gap: var(--mc-gap-card);
        }
        .card {
          background: var(--mc-bg-card);
          border: 1px solid var(--mc-border-subtle);
          border-radius: var(--mc-radius-card);
          padding: var(--mc-pad-card);
        }
        .card--empty { border-color: rgba(255, 107, 107, 0.35); }
        .card h2 {
          margin: 0; font-size: 13px; font-weight: 600;
          letter-spacing: 0.05em; text-transform: uppercase;
        }

        /* Labels & inputs */
        label {
          display: block; font-size: 11px; letter-spacing: 0.05em;
          text-transform: uppercase; color: var(--mc-text-secondary);
          margin: 10px 0 4px;
        }
        input, select, textarea {
          width: 100%; box-sizing: border-box;
          font-family: inherit; font-size: 14px;
          background: var(--mc-bg-secondary);
          color: var(--mc-text-primary);
          border: 1px solid var(--mc-border-input);
          border-radius: var(--mc-radius-input);
          padding: 8px 10px;
          transition: border-color 0.15s;
        }
        input:focus, select:focus, textarea:focus {
          outline: none; border-color: var(--mc-accent);
        }

        /* Primary button */
        .btn-primary {
          background: var(--mc-accent);
          color: var(--mc-bg-primary);
          border: 0; border-radius: var(--mc-radius-btn);
          padding: 8px 16px; font-weight: 600;
          cursor: pointer; font-family: inherit; font-size: 13px;
        }
        .btn-primary:hover { opacity: 0.88; }

        /* Ghost button */
        .btn-ghost {
          background: transparent;
          color: var(--mc-accent);
          border: 1px solid color-mix(in srgb, var(--mc-accent) 40%, transparent);
          border-radius: var(--mc-radius-btn);
          padding: 6px 12px; cursor: pointer;
          font-family: inherit; font-size: 13px;
        }
        .btn-ghost:hover {
          background: color-mix(in srgb, var(--mc-accent) 10%, transparent);
        }

        /* Feedback */
        .feedback { font-size: 13px; min-height: 18px; }
        .feedback.ok   { color: var(--mc-color-ok); }
        .feedback.err  { color: var(--mc-color-err); }
        .feedback.warn { color: var(--mc-color-warn); }

        /* Utility */
        .row   { display: flex; align-items: center; gap: 10px; margin-top: 14px; }
        .empty { color: var(--mc-text-secondary); padding: 32px; text-align: center; }
        .badge {
          font-size: 11px; font-weight: 600;
          letter-spacing: 0.05em; text-transform: uppercase;
        }
        .badge--empty { color: var(--mc-color-err); margin-left: auto; }
      `;
    }
  }

  // -------------------------------------------------------------------------
  // 3. Export
  // -------------------------------------------------------------------------

  global.McPanel = { Base: McPanelBase, tokens };

})(typeof window !== "undefined" ? window : globalThis);
