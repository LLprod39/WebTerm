import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";
import "./styles/fonts.css";
import "./styles/enterprise-light.css";
import "./styles/enterprise-dark.css";
import "./boardui/styles/boardui-bridge.css";

createRoot(document.getElementById("root")!).render(<App />);
