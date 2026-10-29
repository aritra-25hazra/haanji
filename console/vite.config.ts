import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Everything the console needs comes from the engine, reached through /engine/.
// Vite proxies it here; vercel.json rewrites it in production; nginx.conf
// proxies it in the compose stack. The prefix is stripped on the way through.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/engine": {
        target: process.env.HAANJI_ENGINE ?? "http://localhost:8090",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/engine/, ""),
      },
    },
  },
  // Hidden source maps: kept for error tooling, never referenced from the
  // served bundle.
  build: { outDir: "dist", sourcemap: "hidden" },
});
