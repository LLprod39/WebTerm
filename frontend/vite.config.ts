import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, fileURLToPath(new URL(".", import.meta.url)), [
    "WEBTERM_",
    "VITE_DJANGO_URL",
  ]);
  const target =
    process.env.WEBTERM_BACKEND_URL ||
    process.env.VITE_DJANGO_URL ||
    env.WEBTERM_BACKEND_URL ||
    env.VITE_DJANGO_URL ||
    "http://127.0.0.1:9000";
  const allowedHosts = (
    process.env.WEBTERM_FRONTEND_ALLOWED_HOSTS ||
    env.WEBTERM_FRONTEND_ALLOWED_HOSTS ||
    ""
  )
    .split(",")
    .map((host) => host.trim())
    .filter((host) => host && host !== "*");
  return {
    cacheDir: `node_modules/.vite-${new URL(target).port || new URL(target).hostname}`,
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      strictPort: true,
      allowedHosts,
      watch: {
        ignored: [
          "**/storybook-static/**",
          "**/artifacts/**",
          "**/playwright-report*/**",
          "**/test-results*/**",
        ],
      },
      proxy: {
        "/api/": { target, changeOrigin: false },
        "/servers/api/": { target, changeOrigin: false },
        "/ws/": { target, ws: true, changeOrigin: false },
      },
    },
    preview: { allowedHosts },
    build: {
      target: "es2022",
      sourcemap: false,
      manifest: true,
      chunkSizeWarningLimit: 650,
    },
  };
});
