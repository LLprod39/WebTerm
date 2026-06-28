import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Puzzle } from "lucide-react";

import { fetchPluginPage } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { QueryStateBlock, SectionCard } from "@/components/ui/page-shell";
import { PluginErrorBoundary } from "./PluginErrorBoundary";
import {
  buildDynamicFrontendBundleSrcDoc,
  DYNAMIC_FRONTEND_RENDERERS,
  frontendBundleRuntime,
} from "./pluginDynamicBundleFrame";

function PluginPageHostInner() {
  const { pluginId = "", pageId = "" } = useParams();
  const pageQuery = useQuery({
    queryKey: ["plugins", "page", pluginId, pageId],
    queryFn: () => fetchPluginPage(pluginId, pageId),
    retry: false,
    enabled: Boolean(pluginId && pageId),
  });

  const page = pageQuery.data?.page;
  const title = String(page?.title || pageId || "Plugin page");
  const path = String(page?.path || "");
  const renderer = String(page?.renderer || "");
  const runtime = frontendBundleRuntime(page);
  const runtimeRenderer = String(runtime?.renderer || "");
  const runtimeBundleUrl = String(runtime?.bundle_url || "");
  const runtimeBundleSha256 = String(runtime?.bundle_sha256 || "");
  const dynamicBundleSrcDoc = runtime && DYNAMIC_FRONTEND_RENDERERS.has(runtimeRenderer) && runtimeBundleUrl && runtimeBundleSha256
    ? buildDynamicFrontendBundleSrcDoc({
        title,
        pluginId,
        pageId,
        runtime: {
          renderer: runtimeRenderer,
          bundle_url: runtimeBundleUrl,
          bundle_sha256: runtimeBundleSha256,
        },
      })
    : "";
  const sandbox = page?.sandbox && typeof page.sandbox === "object" ? page.sandbox as Record<string, unknown> : {};
  const srcdoc = String(sandbox.srcdoc || "");
  const allowForms = Boolean(sandbox.allow_forms);
  const allowPopups = Boolean(sandbox.allow_popups);
  const sandboxTokens = [allowForms ? "allow-forms" : "", allowPopups ? "allow-popups" : ""].filter(Boolean).join(" ");

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6 lg:px-8">
      <Button asChild variant="ghost" size="sm">
        <Link to="/settings/plugins">
          <ArrowLeft className="h-4 w-4" />
          Plugins
        </Link>
      </Button>

      <QueryStateBlock
        loading={pageQuery.isLoading}
        error={pageQuery.error}
        errorText="Plugin page is unavailable or the plugin is disabled."
      >
        <SectionCard
          title={title}
          description="Enabled plugin page"
          icon={<Puzzle className="h-4 w-4" />}
        >
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">{pluginId}</Badge>
              <Badge variant="secondary">{pageId}</Badge>
              {path ? <Badge variant="outline">{path}</Badge> : null}
            </div>
            {renderer === "iframe_sandbox" && srcdoc ? (
              <iframe
                title={title}
                sandbox={sandboxTokens}
                srcDoc={srcdoc}
                className="min-h-[520px] w-full rounded-lg border border-border/70 bg-background"
                referrerPolicy="no-referrer"
              />
            ) : dynamicBundleSrcDoc ? (
              <iframe
                title={title}
                sandbox="allow-scripts"
                srcDoc={dynamicBundleSrcDoc}
                className="min-h-[520px] w-full rounded-lg border border-border/70 bg-background"
                referrerPolicy="no-referrer"
              />
            ) : (
              <div className="rounded-lg border border-border/70 bg-secondary/15 px-4 py-5 text-sm leading-6 text-muted-foreground">
                No plugin-provided page content is configured.
              </div>
            )}
          </div>
        </SectionCard>
      </QueryStateBlock>
    </div>
  );
}

export default function PluginPageHost() {
  const { pluginId = "", pageId = "" } = useParams();
  return (
    <PluginErrorBoundary pluginId={pluginId} surface={`page:${pageId}`}>
      <PluginPageHostInner />
    </PluginErrorBoundary>
  );
}
