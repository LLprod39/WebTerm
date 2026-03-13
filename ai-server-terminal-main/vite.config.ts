import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

const DOMAIN_AUTH_HEADERS = [
  "x-forwarded-user",
  "x-remote-user",
  "remote-user",
  "x-auth-request-user",
  "x-forwarded-preferred-username",
];

function copyHeader(proxyReq: { setHeader: (name: string, value: string) => void }, req: { headers: Record<string, string | string[] | undefined> }, headerName: string) {
  const raw = req.headers[headerName];
  if (!raw) return;
  const value = Array.isArray(raw) ? raw.join(",") : raw;
  proxyReq.setHeader(headerName, value);
}

function copyProxyHeaders(proxyReq: { setHeader: (name: string, value: string) => void }, req: { headers: Record<string, string | string[] | undefined> }) {
  copyHeader(proxyReq, req, "cookie");
  for (const headerName of DOMAIN_AUTH_HEADERS) {
    copyHeader(proxyReq, req, headerName);
  }
}

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return;
          }

          if (id.includes("@xterm") || id.includes("xterm")) {
            return "terminal-vendor";
          }
          if (id.includes("@xyflow") || id.includes("zustand")) {
            return "flow-vendor";
          }
          if (
            id.includes("react-markdown") ||
            id.includes("remark-") ||
            id.includes("rehype") ||
            id.includes("micromark") ||
            id.includes("mdast") ||
            id.includes("hast") ||
            id.includes("unist") ||
            id.includes("vfile") ||
            id.includes("property-information") ||
            id.includes("parse-entities") ||
            id.includes("character-entities") ||
            id.includes("comma-separated-tokens") ||
            id.includes("space-separated-tokens") ||
            id.includes("style-to-object") ||
            id.includes("style-to-js") ||
            id.includes("html-url-attributes") ||
            id.includes("trim-lines") ||
            id.includes("bail") ||
            id.includes("devlop") ||
            id.includes("inline-style-parser") ||
            id.includes("hastscript")
          ) {
            return "content-vendor";
          }
          if (
            id.includes("recharts") ||
            id.includes("framer-motion") ||
            id.includes("embla-carousel-react") ||
            id.includes("d3-") ||
            id.includes("lodash") ||
            id.includes("decimal-js-light") ||
            id.includes("react-smooth") ||
            id.includes("victory-vendor")
          ) {
            return "visual-vendor";
          }
          if (
            id.includes("@radix-ui") ||
            id.includes("cmdk") ||
            id.includes("vaul") ||
            id.includes("@floating-ui") ||
            id.includes("react-remove-scroll") ||
            id.includes("react-style-singleton") ||
            id.includes("aria-hidden") ||
            id.includes("use-sidecar") ||
            id.includes("use-callback-ref")
          ) {
            return "ui-vendor";
          }
          if (id.includes("lucide-react")) {
            return "icons-vendor";
          }
          return "vendor";
        },
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 8080,
    allowedHosts: true,
    hmr: {
      overlay: false,
    },
    proxy: {
      "/api": {
        target: process.env.VITE_DJANGO_URL || "http://127.0.0.1:9000",
        changeOrigin: false,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, req) => {
            copyProxyHeaders(proxyReq, req as { headers: Record<string, string | string[] | undefined> });
          });
        },
      },
      "/servers/api": {
        target: process.env.VITE_DJANGO_URL || "http://127.0.0.1:9000",
        changeOrigin: false,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, req) => {
            copyProxyHeaders(proxyReq, req as { headers: Record<string, string | string[] | undefined> });
          });
        },
      },
      "/ws": {
        target: process.env.VITE_DJANGO_URL || "http://127.0.0.1:9000",
        changeOrigin: false,
        ws: true,
        configure: (proxy) => {
          // http-proxy does not always forward Cookie on WS upgrade — do it explicitly
          proxy.on("proxyReqWs", (proxyReq, req) => {
            copyProxyHeaders(proxyReq, req as { headers: Record<string, string | string[] | undefined> });
          });
        },
      },
    },
  },
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));
