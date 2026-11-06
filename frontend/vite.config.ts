import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  // `npm run dev` forwards API calls to the backend started by docker compose (see README);
  // API_PROXY points it somewhere else, e.g. a compose stack that only publishes its web port.
  server: {
    proxy: { "/api": loadEnv(mode, ".", "").API_PROXY ?? "http://localhost:8000" },
  },
}));
