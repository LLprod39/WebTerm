import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import path from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), ["VITE_"]);
  const target =
    process.env.VITE_DJANGO_URL ||
    env.VITE_DJANGO_URL ||
    "http://127.0.0.1:9000";

  return {
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "src") },
    },
    server: {
      host: "127.0.0.1",
      port: 8081,
      strictPort: true,
      proxy: {
        "/api/": { target, changeOrigin: false },
        "/servers/api/": { target, changeOrigin: false },
        "/ws/": { target, ws: true, changeOrigin: false },
      },
    },
  };
});