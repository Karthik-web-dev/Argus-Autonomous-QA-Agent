import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: rootDir,
  envDir: path.resolve(rootDir, "../.."),
  define: {
    __ARGUS_FIXTURE_EVENTS__: JSON.stringify(
      path.resolve(rootDir, "../../fixtures/run_events.ndjson"),
    ),
  },
  plugins: [react()],
  resolve: {
    alias: { "@": rootDir },
  },
  server: { port: 5173 },
  preview: { port: 4173 },
});
