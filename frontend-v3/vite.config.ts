import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig, loadEnv } from "vite";

const DOMAIN_AUTH_HEADERS = [
  "x-forwarded-user",
  "x-remote-user",
  "remote-user",
  "x-auth-request-user",
  "x-forwarded-preferred-username",
];

function copyHeader(
  proxyReq: { setHeader: (name: string, value: string) => void },
  req: { headers: Record<string, string | string[] | undefined> },
  headerName: string,
) {
  const raw = req.headers[headerName];
  if (!raw) return;
  const value = Array.isArray(raw) ? raw.join(",") : raw;
  proxyReq.setHeader(headerName, value);
}

function copyProxyHeaders(
  proxyReq: { setHeader: (name: string, value: string) => void },
  req: { headers: Record<string, string | string[] | undefined> },
) {
  copyHeader(proxyReq, req, "cookie");
  for (const headerName of DOMAIN_AUTH_HEADERS) {
    copyHeader(proxyReq, req, headerName);
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target =
    env.VITE_DJANGO_URL ||
    process.env.VITE_DJANGO_URL ||
    "http://127.0.0.1:9000";

  const withProxyHeaders = {
    target,
    changeOrigin: false,
    configure: (proxy: {
      on: (
        event: string,
        listener: (
          proxyReq: { setHeader: (name: string, value: string) => void },
          req: { headers: Record<string, string | string[] | undefined> },
        ) => void,
      ) => void;
    }) => {
      proxy.on("proxyReq", (proxyReq, req) => {
        copyProxyHeaders(proxyReq, req);
      });
    },
  };

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
        "/api/": { ...withProxyHeaders },
        "/servers/api/": { ...withProxyHeaders },
        "/ws/": {
          ...withProxyHeaders,
          ws: true,
          configure: (proxy: {
            on: (
              event: string,
              listener: (
                proxyReq: { setHeader: (name: string, value: string) => void },
                req: { headers: Record<string, string | string[] | undefined> },
              ) => void,
            ) => void;
          }) => {
            // http-proxy does not always forward Cookie on WS upgrade
            proxy.on("proxyReqWs", (proxyReq, req) => {
              copyProxyHeaders(proxyReq, req);
            });
            proxy.on("proxyReq", (proxyReq, req) => {
              copyProxyHeaders(proxyReq, req);
            });
          },
        },
      },
    },
  };
});