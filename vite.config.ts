import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (id.includes("@xterm") || id.includes("xterm")) return "terminal-vendor";
          if (id.includes("@xyflow") || id.includes("zustand")) return "flow-vendor";
          if (id.includes("@radix-ui") || id.includes("cmdk") || id.includes("vaul")) return "ui-vendor";
          if (id.includes("lucide-react")) return "icons-vendor";
          if (id.includes("recharts") || id.includes("framer-motion") || id.includes("d3-")) return "visual-vendor";
          if (id.includes("react-markdown") || id.includes("remark-") || id.includes("rehype")) return "content-vendor";
          return "vendor";
        },
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 8080,
    allowedHosts: true,
    hmr: { overlay: false },
  },
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./ai-server-terminal-main/src"),
    },
  },
}));