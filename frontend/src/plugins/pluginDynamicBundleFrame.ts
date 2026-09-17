export const DYNAMIC_FRONTEND_RENDERERS = new Set(["javascript", "remote", "web_worker"]);

export interface FrontendBundleRuntime {
  renderer?: unknown;
  bundle_url?: unknown;
  bundle_sha256?: unknown;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function safeJson(value: unknown) {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

export function frontendBundleRuntime(surface: { frontend_bundle_runtime?: unknown } | undefined): FrontendBundleRuntime | null {
  const runtime = surface?.frontend_bundle_runtime;
  return runtime && typeof runtime === "object" ? runtime as FrontendBundleRuntime : null;
}

export function buildDynamicFrontendBundleSrcDoc({
  title,
  pluginId,
  pageId,
  surface,
  runtime,
}: {
  title: string;
  pluginId: string;
  pageId: string;
  surface?: string;
  runtime: Required<FrontendBundleRuntime>;
}) {
  const bundleUrl = String(runtime.bundle_url || "");
  const bundleOrigin = new URL(bundleUrl).origin;
  const payload = safeJson({
    pluginId,
    pageId,
    surface: surface || `page:${pageId}`,
    renderer: String(runtime.renderer || ""),
    bundleUrl,
    bundleSha256: String(runtime.bundle_sha256 || "").toLowerCase(),
  });
  const csp = [
    "default-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    "script-src 'unsafe-inline' blob:",
    `connect-src ${bundleOrigin}`,
    "worker-src blob:",
    "style-src 'unsafe-inline'",
    "img-src data: https:",
  ].join("; ");

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="${escapeHtml(csp)}">
  <title>${escapeHtml(title)}</title>
  <style>
    :root { color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; min-height: 100vh; background: transparent; color: CanvasText; }
    #plugin-root { min-height: 100vh; }
    #plugin-status { padding: 16px; font-size: 13px; line-height: 1.5; color: color-mix(in srgb, CanvasText 70%, transparent); }
    #plugin-status[data-error="true"] { color: #b91c1c; }
  </style>
</head>
<body>
  <div id="plugin-root" aria-live="polite"></div>
  <div id="plugin-status">Loading plugin bundle...</div>
  <script>
  (() => {
    const runtime = ${payload};
    const root = document.getElementById("plugin-root");
    const status = document.getElementById("plugin-status");
    const setStatus = (message, isError = false) => {
      if (!status) return;
      status.textContent = message;
      status.dataset.error = isError ? "true" : "false";
    };
    const hex = (buffer) => Array.from(new Uint8Array(buffer)).map((byte) => byte.toString(16).padStart(2, "0")).join("");
    const verifiedBundleUrl = async () => {
      const response = await fetch(runtime.bundleUrl, { credentials: "omit", cache: "no-store", mode: "cors" });
      if (!response.ok) throw new Error("Bundle download failed with status " + response.status);
      const source = await response.arrayBuffer();
      const digest = await crypto.subtle.digest("SHA-256", source);
      const actual = hex(digest);
      if (actual !== runtime.bundleSha256) throw new Error("Bundle SHA-256 mismatch.");
      return URL.createObjectURL(new Blob([source], { type: "text/javascript" }));
    };
    const context = Object.freeze({
      pluginId: runtime.pluginId,
      pageId: runtime.pageId,
      surface: runtime.surface,
      renderer: runtime.renderer,
      mount: root,
      postMessage: (type, payload) => window.parent.postMessage({
        source: "webtrerm-plugin",
        pluginId: runtime.pluginId,
        pageId: runtime.pageId,
        surface: runtime.surface,
        type,
        payload,
      }, "*"),
    });
    const run = async () => {
      const objectUrl = await verifiedBundleUrl();
      if (runtime.renderer === "web_worker") {
        const worker = new Worker(objectUrl, { type: "module" });
        worker.onmessage = (event) => {
          if (event.data && typeof event.data.message === "string") setStatus(event.data.message);
        };
        worker.onerror = (event) => setStatus(event.message || "Plugin worker failed.", true);
        worker.postMessage({ type: "webtrerm:init", context: { pluginId: runtime.pluginId, pageId: runtime.pageId, surface: runtime.surface } });
        setStatus("Plugin worker started.");
        return;
      }
      const module = await import(objectUrl);
      const renderer = module.default || module.render || window.WebTrermPluginBundle?.render;
      if (typeof renderer !== "function") throw new Error("Plugin bundle must export a render function.");
      await renderer(context);
      setStatus("");
    };
    run().catch((error) => setStatus(error?.message || "Plugin bundle failed.", true));
  })();
  </script>
</body>
</html>`;
}
