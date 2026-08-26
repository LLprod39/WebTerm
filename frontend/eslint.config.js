import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["artifacts", "dist"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      // Preserve the pre-v7 Hooks lint contract. The v7 recommended preset also
      // enables React Compiler rules, which require a separate code migration.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
      "react-refresh/only-export-components": [
        "error",
        {
          allowConstantExport: true,
          // Temporary Stage 1 compatibility list. F-08b moves these helpers out
          // of component modules; new mixed exports remain rejected by default.
          allowExportNames: [
            "FALLBACK_FEATURES",
            "LIGHT_UI_STYLES",
            "QUICK_PROMPTS",
            "QUICK_PROMPT_CARDS",
            "UI_STYLE_OPTIONS",
            "actionRiskLabel",
            "actionStatusLabel",
            "actionTone",
            "applyUiStyleToDocument",
            "buildExplicitPayload",
            "checkTitle",
            "cleanStepTitle",
            "countAgentSystemProblems",
            "countHealth",
            "createPermissionModesFromExplicit",
            "createProfileDraft",
            "emptyDraft",
            "formatDateTime",
            "formatProfileDate",
            "formatSync",
            "hasMarkdownTable",
            "healthIcon",
            "inferInventorySkeletonKind",
            "isEnterpriseStyle",
            "isFlowStyle",
            "isFolioStyle",
            "isUiStyleId",
            "keyedPermissionMap",
            "mergeTurnIntoChat",
            "metricToneForHealth",
            "openAssistantDrawer",
            "openCommandPalette",
            "ownerLabel",
            "ownerTone",
            "profileFingerprint",
            "readActiveUiStyle",
            "resolveDocumentUiStyle",
            "readinessLabel",
            "replaceActionInChat",
            "seededSeries",
            "statusLabel",
            "statusTone",
            "useAssistantShell",
            "useConnectionTone",
            "useK8sDensity",
            "useOptionalAssistantShell",
            "useUiStyle",
          ],
        },
      ],
      "@typescript-eslint/no-unused-vars": "off",
    },
  },
  {
    files: ["src/components/ui/**/*.{ts,tsx}", "src/lib/i18n.tsx"],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  },
  {
    files: ["e2e/**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
  {
    files: ["src/pages/AgentsPage.tsx", "src/pages/MCPHubPage.tsx", "src/pages/PipelineEditorPage.tsx"],
    rules: {
      "@typescript-eslint/ban-ts-comment": "off",
    },
  },
);
