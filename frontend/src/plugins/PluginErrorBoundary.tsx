import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

interface PluginErrorBoundaryProps {
  children: ReactNode;
  pluginId?: string;
  surface?: string;
}

interface PluginErrorBoundaryState {
  hasError: boolean;
  message: string;
}

export class PluginErrorBoundary extends Component<PluginErrorBoundaryProps, PluginErrorBoundaryState> {
  state: PluginErrorBoundaryState = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): PluginErrorBoundaryState {
    return { hasError: true, message: error.message || "Plugin surface failed." };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error("Plugin surface render failed", {
        pluginId: this.props.pluginId,
        surface: this.props.surface,
        error,
        componentStack: info.componentStack,
      });
    }
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    const pluginLabel = this.props.pluginId ? ` ${this.props.pluginId}` : "";
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Plugin surface failed</AlertTitle>
        <AlertDescription>
          The plugin{pluginLabel} could not render this surface. Disable or review the plugin before enabling it again.
        </AlertDescription>
      </Alert>
    );
  }
}
