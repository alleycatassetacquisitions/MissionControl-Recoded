/** Mission Control design tokens — shared by every panel. */
export const tokens = {
  bgPrimary: "var(--primary-background-color, #0b1020)",
  bgCard: "var(--card-background-color, #12192e)",
  bgSecondary: "var(--secondary-background-color, #0d1426)",
  textPrimary: "var(--primary-text-color, #e8eefc)",
  textSecondary: "var(--secondary-text-color, #9aa8c7)",
  accent: "var(--primary-color, #00e5ff)",
  magenta: "#ff2bd6",
  borderSubtle: "rgba(255,255,255,0.08)",
  borderInput: "rgba(255,255,255,0.12)",
  colorOk: "#7dffb3",
  colorErr: "#ff6b8a",
  colorWarn: "#ffd770",
  radiusCard: "10px",
  radiusInput: "6px",
  radiusBtn: "6px",
  gapCard: "14px",
  padCard: "16px",
} as const;

export type McTokens = typeof tokens;

/** Inject CSS custom properties into :root once. */
export function injectRootTokens(global: Window & typeof globalThis): void {
  if ((global as { __mcPanelTokensInjected?: boolean }).__mcPanelTokensInjected) {
    return;
  }
  const style = document.createElement("style");
  style.textContent = `:root {
  --mc-bg-primary:    ${tokens.bgPrimary};
  --mc-bg-card:       ${tokens.bgCard};
  --mc-bg-secondary:  ${tokens.bgSecondary};
  --mc-text-primary:  ${tokens.textPrimary};
  --mc-text-secondary:${tokens.textSecondary};
  --mc-accent:        ${tokens.accent};
  --mc-magenta:       ${tokens.magenta};
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
  --ac-cyan:          ${tokens.accent};
  --ac-magenta:       ${tokens.magenta};
  --ac-scan:          rgba(0, 229, 255, 0.09);
}`;
  document.head.appendChild(style);
  (global as { __mcPanelTokensInjected?: boolean }).__mcPanelTokensInjected =
    true;
}
