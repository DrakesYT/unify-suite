import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // `npm run dev` forwards API calls to the backend started by docker compose (see README).
  server: { proxy: { "/api": "http://localhost:8000" } },
});
