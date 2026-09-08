import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The console talks to the Core API through /api, proxied in development so
// that cookies and CORS behave the same way they will behind the reverse proxy
// in production.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Java Core API (when running)
      "/api": { target: process.env.HAANJI_API ?? "http://localhost:8080", changeOrigin: true },
      // Python demo/engine server: live insights, calls, packs, WhatsApp
      "/engine": {
        target: process.env.HAANJI_ENGINE ?? "http://localhost:8090",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/engine/, ""),
      },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
