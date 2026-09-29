/**
 * Mission Control shared panel kit (Lit + TypeScript).
 *
 * Loaded via frontend.extra_module_url before any feature panel:
 *   - /local/shared_libraries/mc-panel.js
 *
 * window.McPanel:
 *   Base   — LitElement McPanelBase
 *   tokens — design tokens
 *   html / css / nothing — re-exported Lit helpers (one Lit runtime)
 */
import { html, css, nothing } from "lit";
import { McPanelBase } from "./base";
import { tokens, injectRootTokens } from "./tokens";

const g = typeof window !== "undefined" ? window : globalThis;

injectRootTokens(g as Window & typeof globalThis);

(g as unknown as Window).McPanel = {
  Base: McPanelBase,
  tokens,
  html,
  css,
  nothing,
};

export { McPanelBase, tokens, html, css, nothing };
