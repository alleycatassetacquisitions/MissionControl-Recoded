import { LitElement, PropertyValues, nothing, html, css } from "lit";
import { property, state } from "lit/decorators.js";
import { sharedStyles, sharedStylesString } from "./styles";
import { tokens } from "./tokens";

/** Minimal HA frontend hass object used by Mission Control panels. */
export interface HassConnection {
  subscribeMessage: (
    callback: (msg: unknown) => void,
    options: Record<string, unknown>
  ) => Promise<() => void>;
  sendMessagePromise: (message: Record<string, unknown>) => Promise<unknown>;
}

export interface HomeAssistant {
  connection: HassConnection;
  callService: (
    domain: string,
    service: string,
    data?: Record<string, unknown>
  ) => Promise<unknown>;
  callWS: <T = unknown>(message: Record<string, unknown>) => Promise<T>;
  states?: Record<
    string,
    { state: string; attributes: Record<string, unknown> }
  >;
}

export type FeedbackKind = "ok" | "err" | "warn";

/**
 * Typed Lit base for every Mission Control panel_custom module.
 *
 * Prefer overriding `render()` with Lit templates.
 * Set `legacyPaint = true` and implement `_render()` / `_boot()` only while
 * porting large imperative panels onto this LitElement base.
 */
export class McPanelBase extends LitElement {
  static override styles = [sharedStyles];

  static sharedStyles(): string {
    return sharedStylesString();
  }

  @property({ attribute: false }) hass: HomeAssistant | null = null;

  @state() protected _feedbackMsg = "";
  @state() protected _feedbackKind: FeedbackKind | "" = "";

  /**
   * When true, Lit does not rewrite shadow DOM; subclass uses `_render()` /
   * `_boot()` (pre-Lit paint pattern). Default false — use `render()`.
   */
  protected legacyPaint = false;

  private _initialized = false;
  private _fbTimer: ReturnType<typeof setTimeout> | null = null;

  override createRenderRoot(): HTMLElement | DocumentFragment {
    const root = super.createRenderRoot();
    // Adopt shared styles into shadow root for legacyPaint panels too
    if (this.legacyPaint && root instanceof ShadowRoot) {
      const sheet = new CSSStyleSheet();
      sheet.replaceSync(sharedStylesString());
      root.adoptedStyleSheets = [...root.adoptedStyleSheets, sheet];
    }
    return root;
  }

  override update(changed: PropertyValues): void {
    if (this.legacyPaint) {
      if (changed.has("hass") && this.hass && !this._initialized) {
        this._initialized = true;
        const self = this as unknown as {
          _render?: () => void;
          _boot?: () => void | Promise<void>;
        };
        self._render?.();
        void self._boot?.();
      }
      // Clear Lit's update bookkeeping without running LitElement.render(),
      // which would wipe imperative shadow DOM from `_render()`.
      const reactiveUpdate = Object.getPrototypeOf(LitElement.prototype)
        .update as (this: LitElement, changed: PropertyValues) => void;
      reactiveUpdate.call(this, changed);
      return;
    }
    super.update(changed);
  }

  override updated(changed: PropertyValues): void {
    if (this.legacyPaint) return;
    if (changed.has("hass") && this.hass && !this._initialized) {
      this._initialized = true;
      void this._boot?.();
    }
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this._initialized = false;
    if (this._fbTimer) clearTimeout(this._fbTimer);
  }

  protected async _boot(): Promise<void> {
    /* no-op — override in subclass */
  }

  protected _esc(s: unknown): string {
    return String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        (
          ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
          }) as Record<string, string>
        )[c]
    );
  }

  protected _feedback(msg: string, kind: FeedbackKind = "ok"): void {
    if (this._fbTimer) clearTimeout(this._fbTimer);
    this._feedbackMsg = msg;
    this._feedbackKind = kind;
    if (this.legacyPaint) {
      const el = this.renderRoot.querySelector("#feedback") as HTMLElement | null;
      if (el) {
        el.textContent = msg;
        el.className = `feedback ${kind}`;
      }
    }
    if (kind === "ok") {
      this._fbTimer = setTimeout(() => this._clearFeedback(), 3000);
    }
  }

  protected _clearFeedback(): void {
    if (this._fbTimer) clearTimeout(this._fbTimer);
    this._fbTimer = null;
    this._feedbackMsg = "";
    this._feedbackKind = "";
    if (this.legacyPaint) {
      const el = this.renderRoot.querySelector("#feedback") as HTMLElement | null;
      if (el) {
        el.textContent = "";
        el.className = "feedback";
      }
    }
  }

  protected _feedbackTemplate() {
    const kind = this._feedbackKind ? ` ${this._feedbackKind}` : "";
    return html`<span id="feedback" class="feedback${kind}"
      >${this._feedbackMsg}</span
    >`;
  }

  override render(): unknown {
    return nothing;
  }
}

export { html, css, nothing, tokens };
