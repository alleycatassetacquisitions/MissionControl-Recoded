import { defineConfig } from "vite";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const haRoot = path.resolve(root, "..");

/** Multi-entry IIFE build → static www/ paths HA already serves. */
export default defineConfig({
  build: {
    emptyOutDir: false,
    sourcemap: true,
    target: "es2022",
    rollupOptions: {
      input: {
        "mc-panel": path.resolve(root, "src/mc-panel/index.ts"),
      },
      output: {
        format: "iife",
        entryFileNames: () => "mc-panel.js",
        dir: path.resolve(
          haRoot,
          "HA_Component/www/shared_libraries"
        ),
        inlineDynamicImports: true,
        name: "McPanelBundle",
      },
    },
  },
});
