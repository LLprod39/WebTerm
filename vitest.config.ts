import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./ai-server-terminal-main/src/test/setup.ts"],
    include: ["ai-server-terminal-main/src/**/*.{test,spec}.{ts,tsx}"],
    exclude: [
      "ai-server-terminal-main/e2e/**",
      "node_modules/**",
      "dist/**",
    ],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "ai-server-terminal-main", "src"),
    },
  },
});
