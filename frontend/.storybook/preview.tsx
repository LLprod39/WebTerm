import type { Preview } from "@storybook/react-vite";
import "@/styles/tokens.css";
const preview: Preview = {
  globalTypes: {
    theme: {
      description: "Цветовая схема",
      toolbar: {
        title: "Theme",
        icon: "circlehollow",
        items: ["light", "dark"],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: { theme: "light" },
  decorators: [
    (Story, context) => {
      document.documentElement.dataset.theme = context.globals.theme ?? "light";
      return (
        <div style={{ padding: 24, maxWidth: 1100 }}>
          <Story />
        </div>
      );
    },
  ],
  parameters: { layout: "fullscreen" },
};
export default preview;
