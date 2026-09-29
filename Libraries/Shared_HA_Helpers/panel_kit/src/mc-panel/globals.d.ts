/** Ambient types for feature panels that consume window.McPanel (no lit import). */
import type { McPanelBase } from "./base";
import type { tokens } from "./tokens";
import type { html, css, nothing } from "lit";

export {};

declare global {
  interface Window {
    McPanel: {
      Base: typeof McPanelBase;
      tokens: typeof tokens;
      html: typeof html;
      css: typeof css;
      nothing: typeof nothing;
    };
    CoreConfigurator?: {
      getUrl: (hass: unknown, key: string) => Promise<string>;
      getServices: (hass: unknown) => Promise<unknown[]>;
      setService: (
        hass: unknown,
        key: string,
        data: Record<string, unknown>
      ) => Promise<unknown>;
      subscribe: (
        hass: unknown,
        cb: () => void
      ) => Promise<() => void>;
    };
  }
}
