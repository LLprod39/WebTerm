import type { StorybookConfig } from "@storybook/react-vite";
import { fileURLToPath } from "node:url";
const config: StorybookConfig = {
  stories: ["../stories/**/*.stories.@(ts|tsx)"],
  addons: [fileURLToPath(new URL("./static-paths.mjs", import.meta.url))],
  framework: { name: "@storybook/react-vite", options: {} },
  core: { disableTelemetry: true },
  viteFinal: async (config) => {
    const { mergeConfig } = await import("vite");
    return mergeConfig(config, {
      resolve: {
        alias: { "@": fileURLToPath(new URL("../src", import.meta.url)) },
      },
    });
  },
};
export default config;
