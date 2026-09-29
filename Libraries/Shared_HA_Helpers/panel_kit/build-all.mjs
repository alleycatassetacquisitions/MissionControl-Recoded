/**
 * Build McPanel (Vite IIFE, Lit bundled) + feature panels (esbuild IIFE, use window.McPanel).
 */
import { build as viteBuild } from "vite";
import * as esbuild from "esbuild";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(root, "../../..");

console.log("Building mc-panel.js (Lit kit)…");
await viteBuild({
  configFile: false,
  root,
  build: {
    emptyOutDir: false,
    sourcemap: true,
    target: "es2022",
    lib: {
      entry: path.resolve(root, "src/mc-panel/index.ts"),
      name: "McPanelBundle",
      formats: ["iife"],
      fileName: () => "mc-panel.js",
    },
    outDir: path.resolve(root, "../HA_Component/www/shared_libraries"),
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: "mc-panel.js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
});
console.log("  → HA_Component/www/shared_libraries/mc-panel.js");

const panels = [
  {
    in: "src/panels/core-configurator-panel.ts",
    out: path.resolve(
      repo,
      "Apps/Core_Configurator/HA_Component/www/core_configurator/core-configurator-panel.js"
    ),
  },
  {
    in: "src/panels/registration-panel.ts",
    out: path.resolve(
      repo,
      "Apps/Registration/HA_Component/www/registration/registration-panel.js"
    ),
  },
  {
    in: "src/panels/dnn-panel.ts",
    out: path.resolve(
      repo,
      "Apps/Digital_Node_Nexus/HA_Component/www/digital_node_nexus/dnn-panel.js"
    ),
  },
  {
    in: "src/panels/bgc-panel.ts",
    out: path.resolve(
      repo,
      "Apps/Broadcast_Group_Controller/HA_Component/www/broadcast_group_controller/bgc-panel.js"
    ),
  },
  {
    in: "src/panels/alleycattv-panel.ts",
    out: path.resolve(
      repo,
      "Apps/AlleycatTV/HA_Component/www/alleycattv/alleycattv-panel.js"
    ),
  },
  {
    in: "src/panels/alleycattv-content-panel.ts",
    out: path.resolve(
      repo,
      "Apps/AlleycatTV/HA_Component/www/alleycattv/alleycattv-content-panel.js"
    ),
  },
  {
    in: "src/panels/gbn-panel.ts",
    out: path.resolve(
      repo,
      "Apps/Galactic_Bounty_Network/HA_Component/www/gbn/gbn-panel.js"
    ),
  },
  {
    in: "src/panels/bug-buster-panel.ts",
    out: path.resolve(
      repo,
      "Apps/Bug_Buster/HA_Component/www/bug_buster/bug-buster-panel.js"
    ),
  },
];

for (const p of panels) {
  await esbuild.build({
    entryPoints: [path.resolve(root, p.in)],
    outfile: p.out,
    bundle: true,
    format: "iife",
    target: "es2022",
    sourcemap: true,
    // Panels must not embed Lit — they extend window.McPanel.Base
    external: [],
    logLevel: "info",
  });
  console.log(`  → ${p.out}`);
}

console.log("Done.");
