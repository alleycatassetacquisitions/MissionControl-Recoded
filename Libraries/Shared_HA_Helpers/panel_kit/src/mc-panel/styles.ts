import { unsafeCSS, CSSResult } from "lit";

/** Shared panel chrome CSS (string) — Alleycat neon folded in from alleycat-panel.css. */
export const SHARED_STYLES_CSS = `
  :host {
    display: block;
    height: 100%;
    overflow: auto;
    background: var(--mc-bg-primary);
    color: var(--mc-text-primary);
    font-family: "Share Tech Mono", var(--primary-font-family, ui-monospace, system-ui, sans-serif);
    --ac-cyan: var(--mc-accent, #00e5ff);
    --ac-magenta: var(--mc-magenta, #ff2bd6);
    --ac-scan: rgba(0, 229, 255, 0.09);
  }
  .wrap {
    max-width: 980px;
    margin: 0 auto;
    padding: 1rem 1.25rem 3rem;
  }

  .page-header,
  header.page-header {
    display: flex;
    align-items: flex-end;
    gap: 16px;
    padding-bottom: 12px;
    margin-bottom: 20px;
    border-bottom: 1px solid var(--mc-border-subtle);
    box-shadow: 0 0 18px rgba(0, 229, 255, 0.12);
    background-image: repeating-linear-gradient(
      180deg,
      transparent,
      transparent 2px,
      var(--ac-scan) 3px
    );
  }
  .page-header h1,
  h1 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    text-shadow: 0 0 12px rgba(0, 229, 255, 0.35);
  }
  .sub {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--mc-text-secondary);
  }
  .header-actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
    gap: var(--mc-gap-card);
  }
  .card,
  .zone-card,
  .item,
  .pi-card {
    background: var(--mc-bg-card);
    border: 1px solid var(--mc-border-subtle);
    border-radius: var(--mc-radius-card);
    padding: var(--mc-pad-card);
    box-shadow: 0 0 10px rgba(0, 229, 255, 0.08);
  }
  .card--empty {
    border-color: rgba(255, 107, 107, 0.35);
  }
  .card h2,
  .card-header {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .card-body {
    margin-top: 10px;
  }

  label {
    display: block;
    font-size: 11px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--mc-text-secondary);
    margin: 10px 0 4px;
  }
  input,
  select,
  textarea {
    width: 100%;
    box-sizing: border-box;
    font-family: inherit;
    font-size: 14px;
    background: var(--mc-bg-secondary);
    color: var(--mc-text-primary);
    border: 1px solid var(--mc-border-input);
    border-radius: var(--mc-radius-input);
    padding: 8px 10px;
    transition: border-color 0.15s;
  }
  input:focus,
  select:focus,
  textarea:focus {
    outline: none;
    border-color: var(--mc-accent);
  }

  .btn-primary,
  .btn.btn-primary {
    background: var(--mc-accent);
    color: var(--mc-bg-primary);
    border: 0;
    border-radius: var(--mc-radius-btn);
    padding: 8px 16px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    font-size: 13px;
  }
  .btn-primary:hover {
    opacity: 0.88;
  }

  .btn-ghost,
  .btn-secondary,
  .btn.btn-secondary {
    background: transparent;
    color: var(--mc-accent);
    border: 1px solid color-mix(in srgb, var(--mc-accent) 40%, transparent);
    border-radius: var(--mc-radius-btn);
    padding: 6px 12px;
    cursor: pointer;
    font-family: inherit;
    font-size: 13px;
  }
  .btn-ghost:hover,
  .btn-secondary:hover {
    background: color-mix(in srgb, var(--mc-accent) 10%, transparent);
  }

  .btn {
    padding: 8px 18px;
    border-radius: 6px;
    border: none;
    cursor: pointer;
    font-size: 0.9rem;
    font-family: inherit;
  }
  .btn-danger {
    background: transparent;
    color: var(--mc-color-err);
    border: 1px solid var(--mc-color-err);
  }
  .btn-link {
    background: transparent;
    color: var(--mc-accent);
    padding: 4px 8px;
  }

  .feedback {
    font-size: 13px;
    min-height: 18px;
  }
  .feedback.ok {
    color: var(--mc-color-ok);
  }
  .feedback.err {
    color: var(--mc-color-err);
  }
  .feedback.warn {
    color: var(--mc-color-warn);
  }

  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 14px;
  }
  .empty {
    color: var(--mc-text-secondary);
    padding: 32px;
    text-align: center;
  }
  .badge {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .badge--empty {
    color: var(--mc-color-err);
    margin-left: auto;
  }
  .hint {
    color: var(--mc-text-secondary);
    font-size: 0.85rem;
  }
`;

export const sharedStyles: CSSResult = unsafeCSS(SHARED_STYLES_CSS);

export function sharedStylesString(): string {
  return SHARED_STYLES_CSS;
}
