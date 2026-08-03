import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // /api/* goes to the local gateway during dev; in prod, Firebase
    // Hosting rewrites will route /api to Cloud Run instead
    proxy: {
      "/api": "http://localhost:8000",
      "/agent": "http://localhost:8001",
    },
  },
});
