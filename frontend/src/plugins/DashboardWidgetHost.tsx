import { Link } from "react-router-dom";
import { Puzzle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import type { DashboardWidgetConfig } from "@/lib/api";
import { getWidgetStringProp } from "@/components/dashboard/widgetProps";
import { PluginErrorBoundary } from "./PluginErrorBoundary";
import {
  buildDynamicFrontendBundleSrcDoc,
  DYNAMIC_FRONTEND_RENDERERS,
  frontendBundleRuntime,
  type FrontendBundleRuntime,
} from "./pluginDynamicBundleFrame";

export interface PluginDashboardWidgetDescriptor {
  plugin_id: string;
  id: string;
  title?: string;
  description?: string;
  page_id?: string;
  path?: string;
  renderer?: string;
  frontend_bundle_runtime?: FrontendBundleRuntime;
}

export function PluginDashboardWidgetHost({
  config,
  widget,
}: {
  config: DashboardWidgetConfig;
  widget: PluginDashboardWidgetDescriptor;
}) {
  return (
    <PluginErrorBoundary pluginId={widget.plugin_id} surface={`dashboard_widget:${widget.id}`}>
      <PluginDashboardWidgetContent config={config} widget={widget} />
    </PluginErrorBoundary>
  );
}

function PluginDashboardWidgetContent({
  config,
  widget,
}: {
  config: DashboardWidgetConfig;
  widget: PluginDashboardWidgetDescriptor;
}) {
  const title = getWidgetStringProp(config, "customTitle", widget.title || widget.id);
  const pagePath = widget.path || (widget.page_id ? `/plugins/${widget.plugin_id}/${widget.page_id}` : "");
  const runtime = frontendBundleRuntime(widget);
  const runtimeRenderer = String(runtime?.renderer || "");
  const runtimeBundleUrl = String(runtime?.bundle_url || "");
  const runtimeBundleSha256 = String(runtime?.bundle_sha256 || "");
  const dynamicBundleSrcDoc = runtime && DYNAMIC_FRONTEND_RENDERERS.has(runtimeRenderer) && runtimeBundleUrl && runtimeBundleSha256
    ? buildDynamicFrontendBundleSrcDoc({
        title,
        pluginId: widget.plugin_id,
        pageId: widget.page_id || widget.id,
        surface: `dashboard_widget:${widget.id}`,
        runtime: {
          renderer: runtimeRenderer,
          bundle_url: runtimeBundleUrl,
          bundle_sha256: runtimeBundleSha256,
        },
      })
    : "";

  return (
    <SectionCard title={title} icon={<Puzzle className="h-4 w-4" />}>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge label="enabled" tone="success" />
          <Badge variant="outline">{widget.plugin_id}</Badge>
          <Badge variant="secondary">{widget.id}</Badge>
        </div>
        {widget.description ? (
          <p className="text-sm leading-6 text-muted-foreground">{widget.description}</p>
        ) : null}
        {dynamicBundleSrcDoc ? (
          <iframe
            title={title}
            sandbox="allow-scripts"
            srcDoc={dynamicBundleSrcDoc}
            className="min-h-[320px] w-full rounded-lg border border-border/70 bg-background"
            referrerPolicy="no-referrer"
          />
        ) : null}
        {pagePath ? (
          <Button asChild size="sm" variant="outline">
            <Link to={pagePath}>Открыть</Link>
          </Button>
        ) : null}
      </div>
    </SectionCard>
  );
}
