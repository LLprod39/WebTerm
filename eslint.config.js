import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist",
      "node_modules",
      "ai-server-terminal-main/node_modules",
      "ai-server-terminal-main/e2e",
      "venv",
      "venv/**",
      ".codex-logs",
    ],
  },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["ai-server-terminal-main/src/**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/ban-ts-comment": "off",
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-empty-object-type": "off",
      "@typescript-eslint/no-unused-vars": "off",
      "no-empty": "off",
      "prefer-const": "off",
    },
  },
  {
    files: [
      "ai-server-terminal-main/src/components/ui/**/*.{ts,tsx}",
      "ai-server-terminal-main/src/lib/i18n.tsx",
    ],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  },
);
