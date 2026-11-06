import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxy = {
  target: process.env.VITE_BACKEND_PROXY_TARGET || "http://127.0.0.1:8000",
  changeOrigin: true,
  ws: true,
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": apiProxy,
    },
  },
  preview: {
    port: 5173,
    proxy: {
      "/api": apiProxy,
    },
  },
});
