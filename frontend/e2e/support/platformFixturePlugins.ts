import { json } from "./apiHarness";
import { FIXED_DATE } from "./platformFixtureTypes";

const pluginPackage = {
  id: 1,
  plugin_id: "webtrerm.demo-dashboard",
  version: "0.1.0",
  name: "Demo Dashboard Plugin",
  slug: "demo-dashboard",
  publisher: { id: "webtrerm", name: "WebTerm" },
  source: "builtin",
  package_hash: "fixture",
  risk_tier: "read",
  review_status: "verified",
  signature_status: "builtin",
  manifest: {},
};

const demoPermission = {
  scope: "demo.alerts.send",
  reason: "Emit a test audit event.",
  risk_tier: "internal_write",
};

const marketplaceSource = {
  id: 1,
  name: "Private catalog",
  source_url: "local://private-catalog",
  is_enabled: true,
  last_sync_at: FIXED_DATE,
  last_error: "",
};

const marketplaceItem = {
  id: 11,
  source: marketplaceSource,
  plugin_id: "acme.slack-alerts",
  version: "0.1.0",
  manifest: {
    id: "acme.slack-alerts",
    name: "Slack Alerts",
    slug: "slack-alerts",
    version: "0.1.0",
    api_version: "plugins.v1",
    summary: "Send selected automation alerts to Slack.",
    publisher: { id: "acme", name: "Acme Automation", verified: true },
    permissions: [{ scope: "connectors.slack.send", reason: "Send alert messages.", risk_tier: "network_write" }],
  },
  package_url: "local://packages/acme.slack-alerts.wtp",
  compatibility: { api_versions: ["plugins.v1"] },
  compatibility_report: { compatible: true, errors: [], api_version: "plugins.v1", supported_api_versions: ["plugins.v1"] },
  review_status: "verified",
  signature_status: "signed",
  installed: false,
  installation_id: null,
  created_at: FIXED_DATE,
  updated_at: FIXED_DATE,
};

export function handlePluginMockRequest(req: any) {
  if (req.path === "/api/plugins/catalog/" && req.method === "GET") {
    return json({
      success: true,
      summary: { registered: 1, enabled: 0, disabled: 1 },
      plugins: [{
        ...pluginPackage,
        id: "webtrerm.demo-dashboard",
        summary: "Harmless demo plugin for extension wiring.",
        publisher: { id: "webtrerm", name: "WebTerm", verified: true },
        categories: ["dashboard", "demo"],
        permissions: [demoPermission],
        surfaces: { pages: [], dashboard_widgets: [], connectors: [], studio_nodes: [], agent_tools: [], terminal_actions: [], hooks: [] },
        actions: [],
        installation: null,
        enabled: false,
      }],
    });
  }

  if (req.path === "/api/plugins/installed/" && req.method === "GET") {
    return json({
      success: true,
      installations: [{
        id: 1,
        plugin_id: "webtrerm.demo-dashboard",
        status: "disabled",
        settings: {},
        package: pluginPackage,
        installed_at: FIXED_DATE,
        enabled_at: null,
        disabled_at: null,
      }],
    });
  }

  if (req.path === "/api/plugins/installed/1/permissions/" && req.method === "GET") {
    return json({ success: true, permissions: [{ ...demoPermission, granted: false, grant_id: null }] });
  }

  if (req.path === "/api/plugins/installed/1/settings/" && req.method === "GET") {
    return json({
      success: true,
      settings: { display_label: "Plugin Runtime Status" },
      schema: { type: "object", properties: { display_label: { type: "string", default: "Plugin Runtime Status" } } },
      secrets: [],
    });
  }

  if (req.path === "/api/plugins/installed/1/impact/" && req.method === "GET") {
    return json({
      success: true,
      impact: {
        installation_id: 1,
        plugin_id: "webtrerm.demo-dashboard",
        status: "disabled",
        package: {
          id: 1,
          version: "0.1.0",
          review_status: "verified",
          signature_status: "builtin",
          ready_to_enable: true,
          enable_blockers: [],
        },
        surfaces: {
          counts: { pages: 1, dashboard_widgets: 1, connectors: 1, studio_nodes: 1, agent_tools: 1, terminal_actions: 1 },
          items: { pages: [], dashboard_widgets: [], connectors: [], studio_nodes: [], agent_tools: [], terminal_actions: [], hooks: [] },
        },
        permissions: {
          declared: ["demo.alerts.send", "demo.connector.ping"],
          granted: [],
          missing: ["demo.alerts.send", "demo.connector.ping"],
          stale_grants: [],
        },
        secrets: {
          declared: ["demo_api_token"],
          bound: [],
          missing_required: ["demo_api_token"],
        },
        settings: { stored_keys: [], declared_keys: ["display_label"] },
        egress_hosts: ["example.com"],
        uninstall: { soft_supported: true, full_supported: false, reversible: false },
      },
    });
  }

  if (req.path === "/api/plugins/installed/1/soft-uninstall/" && req.method === "POST") {
    return json({ success: true, installation: { id: 1, plugin_id: "webtrerm.demo-dashboard", status: "disabled", settings: {}, package: pluginPackage } });
  }

  if (req.path === "/api/plugins/installed/1/rollback/" && req.method === "POST") {
    return json({ success: true, installation: { id: 1, plugin_id: "webtrerm.demo-dashboard", status: "disabled", settings: {}, package: pluginPackage } });
  }

  if (req.path === "/api/plugins/installed/1/settings/update/" && req.method === "POST") {
    return json({ success: true, settings: req.body?.settings || {} });
  }

  if (req.path === "/api/plugins/installed/1/secrets/bind/" && req.method === "POST") {
    return json({ success: true, settings: {}, schema: {}, secrets: [{ key: req.body?.key || "api_token", label: "API token", kind: "bearer_token", required: true, bound: true, secret_ref: "...3456" }] });
  }

  if (req.path === "/api/plugins/surfaces/" && req.method === "GET") {
    return json({
      success: true,
      surfaces: {
        pages: [{ plugin_id: "webtrerm.demo-dashboard", id: "overview", title: "Demo Plugin Overview", path: "/plugins/webtrerm.demo-dashboard/overview" }],
        dashboard_widgets: [{ plugin_id: "webtrerm.demo-dashboard", id: "demo-health", title: "Plugin Runtime Status", page_id: "overview", path: "/plugins/webtrerm.demo-dashboard/overview" }],
        connectors: [{ plugin_id: "webtrerm.demo-dashboard", id: "demo-connector", title: "Demo Connector", description: "Safe connector stub.", required_secret: "demo_api_token", required_permission: "demo.connector.ping", egress_host: "example.com" }],
        studio_nodes: [],
        agent_tools: [{
          plugin_id: "webtrerm.demo-dashboard",
          id: "demo-connector-ping-tool",
          name: "plugin_webtrerm_demo_dashboard_ping",
          title: "Demo connector ping tool",
          description: "Safe agent tool.",
          required_permission: "demo.connector.ping",
          tool_spec: { category: "general", risk: "network" },
        }],
        terminal_actions: [{
          plugin_id: "webtrerm.demo-dashboard",
          id: "demo-terminal-ping",
          title: "Ping demo connector",
          description: "Safe terminal-side action stub.",
          required_permission: "demo.connector.ping",
          risk_tier: "network_read",
        }],
        hooks: [{
          plugin_id: "webtrerm.demo-dashboard",
          id: "demo-audit-hook",
          event: "plugin.demo.audit",
          title: "Demo audit hook",
          required_permission: "demo.alerts.send",
          risk_tier: "internal_write",
        }],
      },
    });
  }

  if (req.path === "/api/plugins/pages/webtrerm.demo-dashboard/overview/" && req.method === "GET") {
    return json({ success: true, page: { plugin_id: "webtrerm.demo-dashboard", id: "overview", title: "Demo Plugin Overview", path: "/plugins/webtrerm.demo-dashboard/overview" } });
  }

  if (req.path === "/api/plugins/connectors/webtrerm.demo-dashboard/demo-connector/health/" && req.method === "GET") {
    return json({
      success: true,
      health: {
        plugin_id: "webtrerm.demo-dashboard",
        connector_id: "demo-connector",
        status: "healthy",
        connector: { plugin_id: "webtrerm.demo-dashboard", id: "demo-connector", title: "Demo Connector" },
        checks: [{ name: "secret_binding", ok: true, key: "demo_api_token" }, { name: "egress_declaration", ok: true, host: "example.com" }],
      },
    });
  }

  if (req.path === "/api/plugins/connectors/webtrerm.demo-dashboard/demo-connector/ping/" && req.method === "POST") {
    return json({ success: true, status: "ok", connector_id: "demo-connector" });
  }

  if (req.path === "/api/plugins/terminal-actions/webtrerm.demo-dashboard/demo-terminal-ping/execute/" && req.method === "POST") {
    return json({ success: true, status: "ok", message: "Plugin terminal action ping completed.", connector_id: "demo-connector" });
  }

  if (req.path.match(/^\/api\/plugins\/installed\/\d+\/(enable|disable)\/$/) && req.method === "POST") {
    return json({
      success: true,
      installation_id: Number(req.path.split("/")[4]),
      status: req.path.includes("/enable/") ? "enabled" : "disabled",
    });
  }

  if (req.path.match(/^\/api\/plugins\/installed\/\d+\/permissions\/(grant|revoke)\/$/) && req.method === "POST") {
    return json({
      success: true,
      scope: String(req.body?.scope || "demo.alerts.send"),
      granted: req.path.includes("/grant/"),
    });
  }

  if (req.path === "/api/plugins/demo/action/" && req.method === "POST") {
    return json({ success: true, message: "Demo plugin action executed." });
  }

  if (req.path === "/api/plugins/review/packages/" && req.method === "GET") {
    return json({ success: true, packages: [pluginPackage], summary: { pending: 0, total: 1 } });
  }

  if (req.path.match(/^\/api\/plugins\/review\/packages\/\d+\/review\/$/) && req.method === "POST") {
    return json({ success: true, package: { ...pluginPackage, review_status: req.body?.status || "verified", signature_status: "signed" } });
  }

  if (req.path.match(/^\/api\/plugins\/review\/packages\/\d+\/(sign|verify-signature)\/$/) && req.method === "POST") {
    return json({ success: true, package: { ...pluginPackage, signature_status: "signed" } });
  }

  if (req.path === "/api/plugins/marketplace/sources/" && req.method === "GET") {
    return json({ success: true, sources: [marketplaceSource] });
  }

  if (req.path === "/api/plugins/marketplace/sources/" && req.method === "POST") {
    return json({ success: true, source: { ...marketplaceSource, name: req.body?.name || marketplaceSource.name } });
  }

  if (req.path.match(/^\/api\/plugins\/marketplace\/sources\/\d+\/sync\/$/) && req.method === "POST") {
    return json({ success: true, synced: Array.isArray(req.body?.plugins) ? req.body.plugins.length : 1 });
  }

  if (req.path === "/api/plugins/marketplace/catalog/" && req.method === "GET") {
    return json({ success: true, items: [marketplaceItem], summary: { available: 1 } });
  }

  if (req.path === "/api/plugins/marketplace/catalog/11/" && req.method === "GET") {
    return json({ success: true, item: marketplaceItem });
  }

  if (req.path === "/api/plugins/marketplace/catalog/11/install/" && req.method === "POST") {
    return json({ success: true, installation_id: 2, status: "disabled" });
  }

  return null;
}
