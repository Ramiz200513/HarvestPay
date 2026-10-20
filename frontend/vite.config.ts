import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В режиме разработки запросы /api/* проксируются на FastAPI (порт 8000),
// поэтому фронтенд и бэкенд работают как будто на одном адресе — без проблем с CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
