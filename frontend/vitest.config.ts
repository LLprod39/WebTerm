import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary", "lcov", "cobertura"],
      reportsDirectory: "./artifacts/coverage",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/**/*.spec.{ts,tsx}", "src/test/**"],
      thresholds: {
        statements: 19.5,
        branches: 15.6,
        functions: 16.6,
        lines: 20.5,
      },
    },
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    reporters: process.env.CI ? ["default", "junit"] : ["default"],
    outputFile: process.env.CI ? { junit: "./artifacts/frontend-junit.xml" } : undefined,
    testTimeout: 10000,
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
