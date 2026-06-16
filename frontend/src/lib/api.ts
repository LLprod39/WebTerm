import {
  isDemoMode,
  canUseDemoMode,
  enableDemoMode,
  DEMO_SESSION,
  DEMO_BOOTSTRAP,
  DEMO_SETTINGS,
  DEMO_MODELS,
  DEMO_ACTIVITY_LOGS,
  demoSuccess,
} from "./demo";
import { demoMarsFallback } from "./demo-mars";
import type {
  StudioPipelineAssistantPayload,
  StudioPipelineAssistantResponse,
} from "./studioPipelineDraftsApi";

export * from "@/api/agents";
export * from "@/api/linux-ui";
export * from "@/api/mars";
export * from "@/api/monitoring";
export * from "@/api/server-files";
export * from "@/api/server-memory";

const API_BASE = import.meta.env.VITE_API_BASE || "";
const BACKEND_ORIGIN = (
  import.meta.env.VITE_BACKEND_ORIGIN ||
  (import.meta.env.DEV && window.location.port === "8080" ? "http://127.0.0.1:9000" : "")
).replace(/\/$/, "");
const DEFAULT_REQUEST_TIMEOUT_MS = parsePositiveInt(import.meta.env.VITE_API_TIMEOUT_MS, 30_000);
const CSRF_REQUEST_TIMEOUT_MS = parsePositiveInt(import.meta.env.VITE_CSRF_TIMEOUT_MS, 8_000);
let csrfTokenCache: string | null = null;
let csrfTokenRequest: Promise<string | null> | null = null;

type ApiFetchOptions = RequestInit & {
  timeoutMs?: number;
};

function parsePositiveInt(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

async function fetchWithTimeout(input: RequestInfo | URL, init: RequestInit = {}, timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const parentSignal = init.signal;
  const abortFromParent = () => controller.abort();

  if (parentSignal?.aborted) {
    controller.abort();
  } else if (parentSignal) {
    parentSignal.addEventListener("abort", abortFromParent, { once: true });
  }

  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
    parentSignal?.removeEventListener("abort", abortFromParent);
  }
}

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? match[2] : null;
}

function isMutationRequest(method?: string): boolean {
  const normalized = (method || "GET").toUpperCase();
  return !["GET", "HEAD", "OPTIONS", "TRACE"].includes(normalized);
}

function isMarsApiPath(path: string): boolean {
  return path.startsWith("/api/mars/");
}

function isDemoBlackholeApiBase(value: string): boolean {
  return /^https?:\/\/(127\.0\.0\.1|localhost):1\/?$/.test(value);
}

function apiBaseForPath(path: string): string {
  return isMarsApiPath(path) && isDemoBlackholeApiBase(API_BASE) ? "" : API_BASE;
}

async function ensureCsrfToken(forceBackend = false): Promise<string | null> {
  const cookieToken = getCookie("csrftoken");
  if (cookieToken) {
    csrfTokenCache = cookieToken;
    return cookieToken;
  }

  if (csrfTokenCache) {
    return csrfTokenCache;
  }

  if (isDemoMode() && !forceBackend) return null;

  if (!csrfTokenRequest) {
    csrfTokenRequest = fetchWithTimeout(
      `${forceBackend && isDemoBlackholeApiBase(API_BASE) ? "" : API_BASE}/api/auth/csrf/`,
      {
        credentials: "include",
      },
      CSRF_REQUEST_TIMEOUT_MS,
    )
      .then(async (response) => {
        if (!response.ok) {
          return null;
        }
        const ct = response.headers.get("content-type") || "";
        if (ct.includes("text/html")) return null;

        const data = (await response.json().catch(() => null)) as { csrfToken?: unknown } | null;
        const token =
          typeof data?.csrfToken === "string" && data.csrfToken
            ? data.csrfToken
            : getCookie("csrftoken");
        csrfTokenCache = token || null;
        return csrfTokenCache;
      })
      .catch(() => null)
      .finally(() => {
        csrfTokenRequest = null;
      });
  }

  return csrfTokenRequest;
}

async function parseErrorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.error === "string" && data.error) return data.error;
    if (typeof data?.message === "string" && data.message) return data.message;
  } catch {
    // noop
  }
  return `HTTP ${res.status}`;
}

function fallbackToDemoOrThrow<T>(path: string, options: RequestInit, errorMessage: string): T {
  if (isMarsApiPath(path)) {
    throw new Error(`${errorMessage}. MARS requires the Django backend and local worker; demo mode cannot generate interviews.`);
  }
  if (enableDemoMode()) {
    return demoFallback<T>(path, options);
  }
  throw new Error(`${errorMessage}. Start Django or set VITE_ENABLE_DEMO_MODE=true to use demo data.`);
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const forceBackend = isMarsApiPath(path);
  // In demo mode, return mock data for known paths
  if (isDemoMode() && !forceBackend) {
    return demoFallback<T>(path, options);
  }

  let response: Response;
  const { timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS, ...requestOptions } = options;
  try {
    const csrfToken = isMutationRequest(requestOptions.method) ? await ensureCsrfToken(forceBackend) : getCookie("csrftoken");
    response = await fetchWithTimeout(`${apiBaseForPath(path)}${path}`, {
      credentials: "include",
      ...requestOptions,
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
        ...((requestOptions.headers as Record<string, string>) || {}),
      },
    }, timeoutMs);
  } catch (error) {
    // Network error — backend unreachable
    return fallbackToDemoOrThrow<T>(path, requestOptions, isAbortError(error) ? "Backend request timed out" : "Backend unavailable");
  }

  // If server returned HTML instead of JSON (Vite SPA fallback), switch to demo
  const ct = response.headers.get("content-type") || "";
  if (ct.includes("text/html")) {
    return fallbackToDemoOrThrow<T>(path, options, "Backend returned HTML instead of JSON");
  }

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return response.json();
}

/** Provides mock data for known API paths when in demo mode */
function demoFallback<T>(path: string, _options: RequestInit = {}): T {
  if (path.includes("/api/auth/session")) return DEMO_SESSION as T;
  if (path.includes("/api/auth/login")) return { success: true, authenticated: true, next_url: "/servers", user: DEMO_SESSION.user } as T;
  if (path.includes("/api/auth/logout")) return { success: true } as T;
  if (path.includes("/api/auth/ws-token")) return { token: "demo-token" } as T;
  if (path.includes("/frontend/bootstrap")) return DEMO_BOOTSTRAP as T;
  if (path.includes("/ui/capabilities")) {
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      observed_at: new Date().toISOString(),
      capabilities: {
        hostname: "demo-linux",
        current_user: "demo",
        os_name: "Ubuntu 24.04 LTS",
        os_id: "ubuntu",
        kernel: "Linux 6.8.0 x86_64",
        is_systemd: true,
        package_manager: "apt",
        commands: {
          systemctl: true,
          journalctl: true,
          docker: true,
          ss: true,
          ip: true,
          apt: true,
          dnf: false,
          yum: false,
          python3: true,
          bash: true,
          sh: true,
        },
        available_apps: {
          overview: true,
          files: true,
          terminal: true,
          ai: true,
          text_editor: true,
          quick_run: true,
          settings: true,
          services: true,
          logs: true,
          processes: true,
          disk: true,
          network: true,
          docker: true,
          packages: true,
        },
      },
    } as T;
  }
  if (path.includes("/ui/overview")) {
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      observed_at: new Date().toISOString(),
      overview: {
        hostname: "demo-linux",
        current_user: "demo",
        home_path: "/home/demo",
        cwd: "/home/demo",
        os_name: "Ubuntu 24.04 LTS",
        kernel: "Linux 6.8.0-41-generic x86_64",
        uptime_seconds: 86400,
        process_count: 182,
        load: { one: 0.24, five: 0.31, fifteen: 0.28 },
        memory: { total_mb: 4096, used_mb: 1380, percent: 33.7 },
        disk: { mount: "/", total_gb: 79.3, used_gb: 24.1, percent: 30.4 },
      },
    } as T;
  }
  if (path.includes("/ui/settings")) {
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      observed_at: new Date().toISOString(),
      settings: {
        general: {
          hostname: "demo-linux.local",
          timezone: "Asia/Qyzylorda",
          kernel: "6.8.0-41-generic",
          os_release: "PRETTY_NAME=\"Ubuntu 24.04 LTS\"\nNAME=\"Ubuntu\"\nVERSION_ID=\"24.04\"",
          uptime: "up 3 days, 4 hours",
          architecture: "x86_64",
          cpu: "8 AMD EPYC Demo vCPU",
          total_memory: "8.0Gi",
        },
        users: {
          current_user: "demo",
          sudo_group: "sudo:x:27:demo",
          accounts: [
            { name: "demo", uid: "1000", home: "/home/demo", shell: "/bin/bash" },
            { name: "deploy", uid: "1001", home: "/srv/deploy", shell: "/bin/bash" },
          ],
          logged_in: "demo pts/0 2026-03-19 09:42 (192.168.1.15)",
          last_logins: "demo pts/0 192.168.1.15 Fri Mar 19 09:42   still logged in",
        },
        crontab: {
          user_crontab: "*/5 * * * * /usr/local/bin/health-check",
          system_crontab: "SHELL=/bin/sh\n17 * * * * root cd / && run-parts --report /etc/cron.hourly",
          cron_dirs: "-rw-r--r-- 1 root root  72 Mar 19 08:00 certbot\n-rw-r--r-- 1 root root 120 Mar 19 08:05 backups",
          timers: "Fri 2026-03-19 10:00:00 +05 17min left apt-daily.timer apt-daily.service",
        },
        environment: {
          shell: "/bin/bash",
          locale: "LANG=en_US.UTF-8\nLC_TIME=en_US.UTF-8",
          path_directories: ["/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"],
          variables: "HOME=/home/demo\nLANG=en_US.UTF-8\nSHELL=/bin/bash\nUSER=demo",
        },
        security: {
          ssh_config: "PermitRootLogin no\nPasswordAuthentication no\nPubkeyAuthentication yes\nPort 22",
          firewall: "Status: active\n22/tcp ALLOW Anywhere\n80/tcp ALLOW Anywhere",
          failed_logins: "Mar 19 08:17:01 demo-linux sshd[2231]: Failed password for invalid user admin from 203.0.113.17 port 43122 ssh2",
          listening_ports: "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\nLISTEN 0 511 0.0.0.0:80 0.0.0.0:*",
        },
      },
    } as T;
  }
  if (path.includes("/ui/services/logs")) {
    const service = path.includes("service=") ? decodeURIComponent(path.split("service=")[1].split("&")[0] || "nginx.service") : "nginx.service";
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      observed_at: new Date().toISOString(),
      service_logs: {
        service,
        lines: 80,
        source: "journalctl",
        content: [
          "2026-03-19T09:41:02+05:00 demo-linux systemd[1]: Starting nginx.service - A high performance web server...",
          "2026-03-19T09:41:02+05:00 demo-linux systemd[1]: Started nginx.service - A high performance web server.",
          "2026-03-19T09:42:17+05:00 demo-linux nginx[1912]: 127.0.0.1 - - [19/Mar/2026:09:42:17 +0500] \"GET /health HTTP/1.1\" 200 2",
        ].join("\n"),
      },
    } as T;
  }
  if (path.includes("/ui/services/action")) {
    let service = "nginx.service";
    let action = "restart";
    try {
      const body =
        typeof _options.body === "string" && _options.body
          ? (JSON.parse(_options.body) as { service?: string; action?: string })
          : null;
      service = body?.service || service;
      action = body?.action || action;
    } catch {
      // noop
    }
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      performed_at: new Date().toISOString(),
      service_action: {
        success: true,
        service,
        action,
        dangerous: action === "stop",
        output: `Simulated systemctl ${action} ${service}`,
        status_excerpt: `${service} - demo service is active (running)`,
      },
    } as T;
  }
  if (path.includes("/ui/services/")) {
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      observed_at: new Date().toISOString(),
      limit: 120,
      summary: { total: 6, active: 4, failed: 1, inactive: 1, other: 0 },
      services: [
        {
          unit: "nginx.service",
          name: "nginx",
          load: "loaded",
          active: "active",
          sub: "running",
          description: "A high performance web server",
          health: "active",
          is_active: true,
          is_failed: false,
        },
        {
          unit: "docker.service",
          name: "docker",
          load: "loaded",
          active: "active",
          sub: "running",
          description: "Docker Application Container Engine",
          health: "active",
          is_active: true,
          is_failed: false,
        },
        {
          unit: "ssh.service",
          name: "ssh",
          load: "loaded",
          active: "active",
          sub: "running",
          description: "OpenBSD Secure Shell server",
          health: "active",
          is_active: true,
          is_failed: false,
        },
        {
          unit: "my-app.service",
          name: "my-app",
          load: "loaded",
          active: "failed",
          sub: "failed",
          description: "Main application worker",
          health: "failed",
          is_active: false,
          is_failed: true,
        },
        {
          unit: "backup.timer-bridge.service",
          name: "backup.timer-bridge",
          load: "loaded",
          active: "inactive",
          sub: "dead",
          description: "On-demand backup bridge",
          health: "inactive",
          is_active: false,
          is_failed: false,
        },
        {
          unit: "redis.service",
          name: "redis",
          load: "loaded",
          active: "active",
          sub: "running",
          description: "Advanced key-value store",
          health: "active",
          is_active: true,
          is_failed: false,
        },
      ],
    } as T;
  }
  if (path.includes("/ui/processes/action")) {
    let pid = 1912;
    let action = "terminate";
    try {
      const body =
        typeof _options.body === "string" && _options.body
          ? (JSON.parse(_options.body) as { pid?: number; action?: string })
          : null;
      pid = body?.pid || pid;
      action = body?.action || action;
    } catch {
      // noop
    }
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      performed_at: new Date().toISOString(),
      process_action: {
        success: true,
        pid,
        action,
        dangerous: action === "kill_force",
        output: `Simulated ${action} for PID ${pid}`,
        still_running: false,
        process_excerpt: "",
      },
    } as T;
  }
  if (path.includes("/ui/processes/")) {
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      observed_at: new Date().toISOString(),
      processes: {
        limit: 80,
        summary: { total: 182, high_cpu: 2, high_memory: 3 },
        top_cpu: [
          { pid: 1912, user: "www-data", cpu_percent: 34.8, memory_percent: 3.2, elapsed: "01:13:04", command: "nginx", args: "nginx: worker process" },
          { pid: 2421, user: "demo", cpu_percent: 21.4, memory_percent: 5.6, elapsed: "00:18:29", command: "python3", args: "python3 app.py --worker" },
          { pid: 887, user: "root", cpu_percent: 7.3, memory_percent: 1.1, elapsed: "04:12:17", command: "dockerd", args: "/usr/bin/dockerd -H fd://" },
        ],
        top_memory: [
          { pid: 2421, user: "demo", cpu_percent: 21.4, memory_percent: 5.6, elapsed: "00:18:29", command: "python3", args: "python3 app.py --worker" },
          { pid: 1502, user: "postgres", cpu_percent: 2.7, memory_percent: 4.3, elapsed: "03:54:02", command: "postgres", args: "postgres: writer process" },
          { pid: 1912, user: "www-data", cpu_percent: 34.8, memory_percent: 3.2, elapsed: "01:13:04", command: "nginx", args: "nginx: worker process" },
        ],
      },
    } as T;
  }
  if (path.includes("/ui/logs/")) {
    const service = path.includes("service=") ? decodeURIComponent(path.split("service=")[1].split("&")[0] || "") : "";
    const source = path.includes("source=") ? decodeURIComponent(path.split("source=")[1].split("&")[0] || "journal") : "journal";
    const content =
      source === "service" && service
        ? [
            `2026-03-19T09:41:02+05:00 demo-linux systemd[1]: Started ${service}.`,
            `2026-03-19T09:42:17+05:00 demo-linux ${service.replace(".service", "")}[2421]: Request completed in 14ms`,
          ].join("\n")
        : [
            "2026-03-19T09:41:02+05:00 demo-linux kernel: eth0: link becomes ready",
            "2026-03-19T09:42:17+05:00 demo-linux sshd[1822]: Accepted publickey for demo from 10.10.0.12 port 54822 ssh2",
            "2026-03-19T09:43:51+05:00 demo-linux systemd[1]: Started Session 11 of user demo.",
          ].join("\n");
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      observed_at: new Date().toISOString(),
      logs: {
        source,
        service,
        lines: 120,
        available: true,
        content,
        presets: [
          { key: "journal", label: "System Journal", description: "Recent lines from journalctl", available: true },
          { key: "service", label: "Service Journal", description: "Logs for a specific systemd unit", available: true },
          { key: "syslog", label: "syslog", description: "/var/log/syslog", available: true },
          { key: "messages", label: "messages", description: "/var/log/messages", available: false },
          { key: "auth", label: "auth.log", description: "/var/log/auth.log", available: true },
          { key: "nginx_error", label: "nginx error", description: "/var/log/nginx/error.log", available: true },
          { key: "nginx_access", label: "nginx access", description: "/var/log/nginx/access.log", available: true },
          { key: "apache_error", label: "apache error", description: "/var/log/apache2/error.log or /var/log/httpd/error_log", available: false },
          { key: "apache_access", label: "apache access", description: "/var/log/apache2/access.log or /var/log/httpd/access_log", available: false },
        ],
      },
    } as T;
  }
  if (path.includes("/ui/disk/")) {
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      observed_at: new Date().toISOString(),
      disk: {
        summary: {
          mounts: 4,
          critical_mounts: 1,
          top_directory_mb: 12240,
          largest_log_mb: 840,
          cleanup_candidates: 4,
        },
        mounts: [
          { filesystem: "/dev/sda1", mount: "/", size_gb: 79.3, used_gb: 24.1, available_gb: 55.2, percent: 30.4 },
          { filesystem: "/dev/sda2", mount: "/var/lib/docker", size_gb: 48.0, used_gb: 43.8, available_gb: 4.2, percent: 91.2 },
          { filesystem: "tmpfs", mount: "/run", size_gb: 2.0, used_gb: 0.1, available_gb: 1.9, percent: 5.0 },
          { filesystem: "tmpfs", mount: "/dev/shm", size_gb: 2.0, used_gb: 0.0, available_gb: 2.0, percent: 1.0 },
        ],
        top_directories: [
          { path: "/var/lib/docker", size_mb: 12240 },
          { path: "/var/log", size_mb: 1740 },
          { path: "/home/demo", size_mb: 960 },
          { path: "/tmp", size_mb: 620 },
          { path: "/opt", size_mb: 410 },
        ],
        large_logs: [
          { path: "/var/log/nginx/access.log", size_mb: 840 },
          { path: "/var/log/syslog", size_mb: 320 },
          { path: "/var/log/nginx/error.log", size_mb: 108 },
          { path: "/var/log/auth.log", size_mb: 56 },
        ],
        cleanup_candidates: [
          "/tmp/build-cache-20260301",
          "/tmp/worker-dump-8821",
          "/tmp/npm-archive-18",
          "/tmp/render-staging-artifacts",
        ],
      },
    } as T;
  }
  if (path.includes("/ui/packages/")) {
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      observed_at: new Date().toISOString(),
      packages: {
        package_manager: "apt",
        installed: [
          { name: "nginx", version: "1.24.0-2ubuntu7.2" },
          { name: "python3", version: "3.12.3-0ubuntu2" },
          { name: "nodejs", version: "20.11.1-1nodesource1" },
          { name: "redis-server", version: "7:7.0.15-1build2" },
        ],
        updates: [
          "openssl\t3.0.13-0ubuntu3.6",
          "systemd\t255.4-1ubuntu8.8",
          "curl\t8.5.0-2ubuntu10.6",
          "ca-certificates\t20240203",
        ],
        summary: {
          installed_common: 4,
          update_candidates: 4,
        },
      },
    } as T;
  }
  if (path.includes("/ui/docker/logs")) {
    const container = path.includes("container=") ? decodeURIComponent(path.split("container=")[1].split("&")[0] || "web") : "web";
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      observed_at: new Date().toISOString(),
      docker_logs: {
        container,
        lines: 80,
        content: [
          "2026-03-19T10:12:04Z web | listening on :3000",
          "2026-03-19T10:12:21Z web | GET /health 200 3ms",
          "2026-03-19T10:13:05Z web | POST /api/deploy 202 11ms",
        ].join("\n"),
      },
    } as T;
  }
  if (path.includes("/ui/docker/action")) {
    let container = "web";
    let action = "restart";
    try {
      const body =
        typeof _options.body === "string" && _options.body
          ? (JSON.parse(_options.body) as { container?: string; action?: string })
          : null;
      container = body?.container || container;
      action = body?.action || action;
    } catch {
      // noop
    }
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      performed_at: new Date().toISOString(),
      docker_action: {
        success: true,
        container,
        action,
        dangerous: action === "stop",
        output: `Simulated docker ${action} ${container}`,
        inspect_excerpt: "running\tdemo/web:2026.03\t/web",
      },
    } as T;
  }
  if (path.includes("/ui/docker/")) {
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      observed_at: new Date().toISOString(),
      docker: {
        ready: true,
        error: "",
        summary: { total: 4, running: 2, exited: 1, restarting: 1, paused: 0 },
        containers: [
          {
            id: "2f4d8b1c8d2a",
            name: "web",
            image: "demo/web:2026.03",
            state: "running",
            status: "Up 2 hours",
            running_for: "2 hours",
            ports: "0.0.0.0:3000->3000/tcp",
            cpu_percent: "4.18%",
            memory_percent: "12.44%",
            memory_usage: "248MiB / 2GiB",
            network_io: "18MB / 9MB",
            block_io: "1.4GB / 128MB",
          },
          {
            id: "1c1a92e6fbde",
            name: "worker",
            image: "demo/worker:2026.03",
            state: "running",
            status: "Up 2 hours",
            running_for: "2 hours",
            ports: "",
            cpu_percent: "22.10%",
            memory_percent: "18.02%",
            memory_usage: "360MiB / 2GiB",
            network_io: "4MB / 2MB",
            block_io: "860MB / 96MB",
          },
          {
            id: "7d2f43a99111",
            name: "scheduler",
            image: "demo/scheduler:2026.03",
            state: "restarting",
            status: "Restarting (1) 9 seconds ago",
            running_for: "",
            ports: "",
            cpu_percent: "",
            memory_percent: "",
            memory_usage: "",
            network_io: "",
            block_io: "",
          },
          {
            id: "0de2450fa221",
            name: "old-nginx",
            image: "nginx:1.25",
            state: "exited",
            status: "Exited (0) 3 days ago",
            running_for: "",
            ports: "80/tcp",
            cpu_percent: "",
            memory_percent: "",
            memory_usage: "",
            network_io: "",
            block_io: "",
          },
        ],
      },
    } as T;
  }
  if (path.includes("/ui/network/")) {
    return {
      success: true,
      server: { id: 1, name: "demo-linux", host: "192.168.1.10", username: "demo" },
      observed_at: new Date().toISOString(),
      network: {
        tools: { ip: true, ss: true },
        summary: { interfaces: 3, addresses: 5, routes: 4, listening: 6 },
        interfaces: [
          {
            name: "lo",
            state: "UNKNOWN",
            mtu: 65536,
            kind: "loopback",
            mac: "00:00:00:00:00:00",
            flags: ["LOOPBACK", "UP", "LOWER_UP"],
            addresses: [
              { family: "inet", address: "127.0.0.1/8", scope: "host" },
              { family: "inet6", address: "::1/128", scope: "host" },
            ],
          },
          {
            name: "eth0",
            state: "UP",
            mtu: 1500,
            kind: "ether",
            mac: "52:54:00:ab:cd:ef",
            flags: ["BROADCAST", "MULTICAST", "UP", "LOWER_UP"],
            addresses: [
              { family: "inet", address: "192.168.1.10/24", scope: "global" },
              { family: "inet6", address: "fe80::5054:ff:feab:cdef/64", scope: "link" },
            ],
          },
          {
            name: "docker0",
            state: "DOWN",
            mtu: 1500,
            kind: "ether",
            mac: "02:42:ec:2f:4b:7a",
            flags: ["NO-CARRIER", "BROADCAST", "MULTICAST", "UP"],
            addresses: [
              { family: "inet", address: "172.17.0.1/16", scope: "global" },
            ],
          },
        ],
        routes: [
          "default via 192.168.1.1 dev eth0 proto dhcp src 192.168.1.10 metric 100",
          "172.17.0.0/16 dev docker0 proto kernel scope link src 172.17.0.1",
          "192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.10 metric 100",
          "192.168.1.1 dev eth0 proto dhcp scope link src 192.168.1.10 metric 100",
        ],
        listening: [
          { protocol: "tcp", state: "LISTEN", local_address: "0.0.0.0:22", peer_address: "0.0.0.0:*", process: "users:((\"sshd\",pid=957,fd=3))" },
          { protocol: "tcp", state: "LISTEN", local_address: "0.0.0.0:80", peer_address: "0.0.0.0:*", process: "users:((\"nginx\",pid=1912,fd=6))" },
          { protocol: "tcp", state: "LISTEN", local_address: "127.0.0.1:5432", peer_address: "0.0.0.0:*", process: "users:((\"postgres\",pid=1502,fd=7))" },
          { protocol: "tcp", state: "LISTEN", local_address: "0.0.0.0:3000", peer_address: "0.0.0.0:*", process: "users:((\"python3\",pid=2421,fd=12))" },
          { protocol: "udp", state: "UNCONN", local_address: "127.0.0.53%lo:53", peer_address: "0.0.0.0:*", process: "users:((\"systemd-resolved\",pid=618,fd=13))" },
          { protocol: "udp", state: "UNCONN", local_address: "0.0.0.0:68", peer_address: "0.0.0.0:*", process: "users:((\"dhclient\",pid=712,fd=6))" },
        ],
      },
    } as T;
  }
  if (path.includes("/servers/api/") && path.includes("/files/read/")) {
    const filePath = path.includes("path=") ? decodeURIComponent(path.split("path=")[1].split("&")[0] || "/home/demo/nginx.conf") : "/home/demo/nginx.conf";
    return {
      success: true,
      file: {
        path: filePath,
        filename: filePath.split("/").filter(Boolean).pop() || "demo.conf",
        size: 246,
        encoding: "utf-8",
        content: "server {\n    listen 80;\n    server_name demo.local;\n    root /var/www/html;\n}\n",
      },
    } as T;
  }
  if (path.includes("/servers/api/") && path.includes("/files/write/")) {
    let filePath = "/home/demo/nginx.conf";
    let content = "";
    try {
      const body =
        typeof _options.body === "string" && _options.body
          ? (JSON.parse(_options.body) as { path?: string; content?: string })
          : null;
      filePath = body?.path || filePath;
      content = body?.content || content;
    } catch {
      // noop
    }
    return {
      success: true,
      file: {
        path: filePath,
        filename: filePath.split("/").filter(Boolean).pop() || "demo.conf",
        size: content.length,
        encoding: "utf-8",
        content,
      },
    } as T;
  }
  if (path.includes("/servers/api/") && path.includes("/files/chmod/")) {
    let filePath = "/home/demo/deploy.log";
    try {
      const body =
        typeof _options.body === "string" && _options.body
          ? (JSON.parse(_options.body) as { path?: string })
          : null;
      filePath = body?.path || filePath;
    } catch {
      // noop
    }
    return {
      success: true,
      path: filePath.split("/").slice(0, -1).join("/") || "/",
      entry: {
        name: filePath.split("/").filter(Boolean).pop() || "deploy.log",
        path: filePath,
        kind: "file",
        is_dir: false,
        is_symlink: false,
        size: 18432,
        permissions: "-rw-r-----",
        permissions_octal: "0640",
        modified_at: Math.floor(Date.now() / 1000),
      },
    } as T;
  }
  if (path.includes("/servers/api/") && path.includes("/files/chown/")) {
    let filePath = "/home/demo/deploy.log";
    try {
      const body =
        typeof _options.body === "string" && _options.body
          ? (JSON.parse(_options.body) as { path?: string })
          : null;
      filePath = body?.path || filePath;
    } catch {
      // noop
    }
    return {
      success: true,
      path: filePath.split("/").slice(0, -1).join("/") || "/",
      entry: {
        name: filePath.split("/").filter(Boolean).pop() || "deploy.log",
        path: filePath,
        kind: "file",
        is_dir: false,
        is_symlink: false,
        size: 18432,
        permissions: "-rw-r--r--",
        permissions_octal: "0644",
        modified_at: Math.floor(Date.now() / 1000),
      },
    } as T;
  }

  // Settings page
  if (path.includes("/api/settings/activity")) return DEMO_ACTIVITY_LOGS as T;
  if (path.includes("/api/settings")) return DEMO_SETTINGS as T;
  if (path.includes("/api/models/refresh")) {
    const requestedProvider = (() => {
      try {
        const raw = typeof _options.body === "string" ? JSON.parse(_options.body) : null;
        return typeof raw?.provider === "string" ? raw.provider : "gemini";
      } catch {
        return "gemini";
      }
    })();
    const demoModels =
      requestedProvider === "ollama"
        ? ["llama3.2:latest", "qwen2.5-coder:7b"]
        : requestedProvider === "openai"
          ? ["gpt-5-mini"]
          : requestedProvider === "claude"
            ? ["claude-sonnet-4-6"]
            : requestedProvider === "grok"
              ? ["grok-3"]
              : ["gemini-2.0-flash"];
    return { success: true, provider: requestedProvider, models: demoModels, count: demoModels.length } as T;
  }
  if (path.includes("/api/models")) return DEMO_MODELS as T;

  // Admin dashboard — must match AdminDashboardData shape
  if (path.includes("/api/admin/dashboard")) return {
    success: true,
    data: {
      online_users: { count: 1, total_registered: 1, users: [{ username: "demo", action: "login", time: new Date().toISOString() }] },
      ai: { requests_today: 0 },
      terminals: { active: 0, connections: [] },
      agents: { running: 0, today: 0, succeeded_24h: 0, failed_24h: 0, success_rate: 0 },
      api_usage: {},
      api_calls_today: 0,
      providers: { gemini: { enabled: true, model: "gemini-2.0-flash" } },
      servers: { total: 3, active: 2 },
      tasks: { total: 0, in_progress: 0 },
      hourly_activity: [],
      top_users: [{ username: "demo", total: 5, ai_requests: 2, terminal_sessions: 3 }],
      recent_activity: [{ user: "demo", category: "auth", action: "login", time: new Date().toISOString() }],
      fleet_health: { avg_cpu: 25, avg_memory: 40, avg_disk: 35, healthy: 2, warning: 0, critical: 0, unreachable: 1 },
      active_alerts_count: 0,
      alerts: [],
      app_version: "demo",
    },
  } as T;
  if (path.includes("/api/admin/users/sessions")) return { success: true, online_count: 1, total_registered: 1, active_today: 1, sessions: [] } as T;
  if (path.includes("/api/admin/users/activity")) return { success: true, total: 0, events: [] } as T;

  // Monitoring dashboard — must match MonitoringDashboard shape
  if (path.includes("/servers/api/monitoring/config")) return {
    success: true,
    thresholds: { cpu_warn: 80, cpu_crit: 95, mem_warn: 85, mem_crit: 95, disk_warn: 80, disk_crit: 90 },
    stats: { total_checks: 0, active_alerts: 0, last_check_at: null, monitored_servers: 0 },
  } as T;
  if (path.includes("/servers/api/monitoring/dashboard")) return {
    success: true,
    servers: [],
    alerts: [],
    summary: { total_servers: 3, healthy: 2, warning: 0, critical: 0, unreachable: 1, unknown: 0, active_alerts: 0, avg_cpu: 25, avg_memory: 40, avg_disk: 35 },
    recent_activity: [],
  } as T;
  if (path.includes("/servers/api/monitoring/status")) return {
    success: true,
    servers: [],
    summary: { total_servers: 0, healthy: 0, warning: 0, critical: 0, unreachable: 0, unknown: 0, stale: 0 },
    meta: { stale_after_seconds: 300, latest_checked_at: null, has_stale: false },
  } as T;
  if (path.includes("/servers/api/monitoring/refresh")) return {
    success: true,
    servers: [],
    summary: { total_servers: 0, healthy: 0, warning: 0, critical: 0, unreachable: 0, unknown: 0, stale: 0 },
    meta: { stale_after_seconds: 300, latest_checked_at: null, has_stale: false },
    refreshed: true,
  } as T;

  // Agents
  if (path.includes("/servers/api/agents/dashboard")) return { success: true, active: [], recent: [] } as T;
  if (path.includes("/servers/api/agents/schedules/dispatch/")) {
    return {
      success: true,
      summary: {
        scanned: 1,
        due: 1,
        launched_agents: 1,
        runs_created: 1,
        background_runs: 1,
        mini_runs: 0,
        skipped: 0,
        skip_reasons: {
          not_due: 0,
          no_servers: 0,
          active_run: 0,
          limit: 0,
          launch_rejected: 0,
          error: 0,
        },
        errors: [],
      },
      generated_at: new Date().toISOString(),
    } as T;
  }
  if (path.includes("/servers/api/agents/schedules/")) {
    return {
      success: true,
      summary: {
        total_scheduled: 1,
        enabled: 1,
        paused: 0,
        due_now: 1,
        active_runs: 0,
      },
      generated_at: new Date().toISOString(),
      scheduled_agents: [
        {
          id: 1,
          name: "Demo Deploy Watcher",
          mode: "full",
          mode_display: "Full Agent (ReAct)",
          agent_type: "deploy_watcher",
          agent_type_display: "Deploy Watcher",
          server_count: 1,
          server_names: ["demo-linux"],
          schedule_minutes: 15,
          is_enabled: true,
          commands: [],
          ai_prompt: "Track deploy drift",
          goal: "Check services after deploy and verify health.",
          system_prompt: "",
          max_iterations: 8,
          allow_multi_server: false,
          last_run_at: new Date(Date.now() - 60 * 60_000).toISOString(),
          last_run_status: "completed",
          last_run_id: 1,
          active_run_id: null,
          schedule_state: "due",
          due_now: true,
          next_due_at: new Date(Date.now() - 30 * 60_000).toISOString(),
          next_due_in_seconds: 0,
        },
      ],
    } as T;
  }
  if (path.includes("/servers/api/agents/templates")) return { success: true, templates: [] } as T;
  if (path.includes("/servers/api/agents/runs/") && path.includes("/events/")) {
    return { success: true, events: [], total: 0 } as T;
  }
  if (path.includes("/servers/api/agents/runs")) return { success: true, runs: [] } as T;
  if (path.includes("/servers/api/watchers/drafts/") && path.includes("/launch/")) {
    return {
      success: true,
      draft: {
        id: 1,
        server_id: 1,
        server_name: "demo-linux",
        severity: "warning",
        recommended_role: "infra_scout",
        objective: "Investigate service drift on demo-linux",
        reasons: ["Demo mode watcher draft"],
        memory_excerpt: ["Nginx was restarted during the last deploy"],
        status: "acknowledged",
        acknowledged_at: new Date().toISOString(),
        acknowledged_by: "demo",
        resolved_at: null,
        first_seen_at: new Date().toISOString(),
        last_seen_at: new Date().toISOString(),
        metadata: { launch_count: 1 },
      },
      agent_id: 1,
      run_id: 1,
      status: "pending",
    } as T;
  }
  if (path.includes("/servers/api/agents")) return { success: true, agents: [] } as T;
  if (path.includes("/servers/api/alerts")) return { success: true, alerts: [] } as T;
  if (path.includes("/servers/api/") && path.includes("/files/")) return {
    success: true,
    path: "/home/demo",
    home_path: "/home/demo",
    parent_path: "/home",
    entries: [
      {
        name: "deploy.log",
        path: "/home/demo/deploy.log",
        kind: "file",
        is_dir: false,
        is_symlink: false,
        size: 18432,
        permissions: "-rw-r--r--",
        permissions_octal: "0644",
        modified_at: Math.floor(Date.now() / 1000) - 3600,
      },
      {
        name: "releases",
        path: "/home/demo/releases",
        kind: "dir",
        is_dir: true,
        is_symlink: false,
        size: 0,
        permissions: "drwxr-xr-x",
        permissions_octal: "0755",
        modified_at: Math.floor(Date.now() / 1000) - 86400,
      },
    ],
  } as T;
  if (path.includes("/servers/api/global-context")) return { rules: "", forbidden_commands: [], required_checks: [], environment_vars: {} } as T;
  if (path.includes("/servers/api/master-password")) return { has_master_password: false, success: true } as T;
  if (path.includes("/knowledge")) return { success: true, items: [], categories: [] } as T;
  if (path.includes("/shares")) return { success: true, shares: [] } as T;

  if (path.includes("/api/health")) return { status: "ok" } as T;
  if (path.includes("/api/access/users")) return {
    success: true,
    features: ACCESS_FEATURE_OPTIONS,
    users: [
      {
        id: 1,
        username: "demo",
        email: "demo@example.com",
        is_staff: true,
        is_active: true,
        is_superuser: false,
        access_profile: "admin_full",
        groups: [{ id: 1, name: "Operators" }],
        effective_permissions: {
          servers: true,
          dashboard: true,
          agents: true,
          studio: true,
          studio_pipelines: true,
          studio_runs: true,
          studio_agents: true,
          studio_skills: true,
          studio_mcp: true,
          studio_notifications: true,
          kubernetes: false,
          mars: false,
          settings: true,
          orchestrator: true,
          knowledge_base: true,
        },
        explicit_permissions: {},
        group_permissions: { servers: true, studio: true, studio_pipelines: true, studio_runs: true, studio_agents: true, studio_skills: true, studio_mcp: true, studio_notifications: true },
        group_permission_sources: {
          servers: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_pipelines: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_runs: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_agents: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_skills: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_mcp: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_notifications: [{ group_id: 1, group_name: "Operators", allowed: true }],
        },
        permission_sources: {
          servers: "group_explicit",
          dashboard: "staff_default",
          agents: "staff_default",
          studio: "group_explicit",
          studio_pipelines: "group_explicit",
          studio_runs: "group_explicit",
          studio_agents: "group_explicit",
          studio_skills: "group_explicit",
          studio_mcp: "group_explicit",
          studio_notifications: "group_explicit",
          kubernetes: "explicit_opt_in",
          mars: "explicit_opt_in",
          settings: "staff_default",
          orchestrator: "staff_default",
          knowledge_base: "staff_default",
        },
      },
    ],
  } as T;
  if (path.includes("/api/access/groups")) return {
    success: true,
    features: ACCESS_FEATURE_OPTIONS,
    groups: [
      {
        id: 1,
        name: "Operators",
        member_count: 1,
        members: [{ id: 1, username: "demo" }],
        explicit_permissions: { servers: true, studio: true, studio_pipelines: true, studio_runs: true, studio_agents: true, studio_skills: true, studio_mcp: true, studio_notifications: true },
      },
    ],
  } as T;
  if (path.includes("/api/access/group-permissions")) return {
    success: true,
    features: ACCESS_FEATURE_OPTIONS,
    permissions: [
      { id: 1, group_id: 1, group_name: "Operators", feature: "servers", feature_display: "Servers", allowed: true },
      { id: 2, group_id: 1, group_name: "Operators", feature: "studio", feature_display: "Studio", allowed: true },
      { id: 3, group_id: 1, group_name: "Operators", feature: "studio_pipelines", feature_display: "Studio Pipelines", allowed: true },
      { id: 4, group_id: 1, group_name: "Operators", feature: "studio_runs", feature_display: "Studio Runs", allowed: true },
      { id: 5, group_id: 1, group_name: "Operators", feature: "studio_agents", feature_display: "Studio Agents", allowed: true },
      { id: 6, group_id: 1, group_name: "Operators", feature: "studio_skills", feature_display: "Studio Skills", allowed: true },
      { id: 7, group_id: 1, group_name: "Operators", feature: "studio_mcp", feature_display: "Studio MCP", allowed: true },
      { id: 8, group_id: 1, group_name: "Operators", feature: "studio_notifications", feature_display: "Studio Notifications", allowed: true },
    ],
  } as T;
  if (path.includes("/api/access/permissions")) return {
    success: true,
    features: ACCESS_FEATURE_OPTIONS,
    permissions: [],
    group_permissions: [],
  } as T;
  if (path.includes("/api/studio/share-users")) return [{ id: 1, username: "demo", email: "demo@example.com" }] as T;
  if (path.includes("/api/studio/assistant/drafts")) return [] as T;
  if (path.includes("/api/studio/node-manifests")) return { version: 1, count: 0, nodes: [] } as T;
  if (path.includes("/api/studio/capabilities")) return {
    strategy: {
      mode: "minimal_universal_nodes",
      service_specific_work: "mcp_plus_skills",
      default_execution_node: "agent/mcp_call",
      approval_node: "logic/human_approval",
      verification_nodes: ["ops/http_check", "output/report", "agent/mcp_call"],
    },
    nodes: [],
    capability_packs: [],
    resources: { mcp_servers: [], skills: [], server_count: 0 },
    task_families: [],
  } as T;
  if (path.includes("/api/studio/templates")) return [] as T;
  if (path.includes("/api/studio/pipelines")) return [] as T;
  if (path.includes("/api/studio/runs")) return [] as T;
  if (path.includes("/api/studio/agents")) return [] as T;
  if (path.includes("/api/studio/mcp/templates")) return [] as T;
  if (path.includes("/api/studio/mcp")) return [] as T;
  if (path.includes("/api/studio/triggers")) return [] as T;
  if (path.includes("/api/studio/notifications")) return { success: true } as T;
  if (path.includes("/api/studio/servers")) return [] as T;
  if (path.includes("/api/studio/skills")) return [] as T;
  const marsFallback = demoMarsFallback<T>(path, _options);
  if (marsFallback !== undefined) return marsFallback;

  // Generic fallback
  return demoSuccess() as T;
}

export type ServerStatus = "online" | "offline" | "unknown";

export type StudioSectionFeature =
  | "studio_pipelines"
  | "studio_runs"
  | "studio_agents"
  | "studio_skills"
  | "studio_mcp"
  | "studio_notifications";

export type FeatureFlag =
  | "servers"
  | "dashboard"
  | "agents"
  | "studio"
  | StudioSectionFeature
  | "kubernetes"
  | "mars"
  | "settings"
  | "orchestrator"
  | "knowledge_base";

export const ACCESS_FEATURE_OPTIONS: Array<{ value: FeatureFlag; label: string }> = [
  { value: "servers", label: "Servers" },
  { value: "dashboard", label: "Dashboard" },
  { value: "agents", label: "Agents" },
  { value: "studio", label: "Studio" },
  { value: "studio_pipelines", label: "Studio Pipelines" },
  { value: "studio_runs", label: "Studio Runs" },
  { value: "studio_agents", label: "Studio Agents" },
  { value: "studio_skills", label: "Studio Skills" },
  { value: "studio_mcp", label: "Studio MCP" },
  { value: "studio_notifications", label: "Studio Notifications" },
  { value: "kubernetes", label: "Kubernetes" },
  { value: "mars", label: "MARS" },
  { value: "settings", label: "Settings" },
  { value: "orchestrator", label: "Orchestrator" },
  { value: "knowledge_base", label: "Knowledge Base" },
];

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  is_superuser?: boolean;
  access_profile?: string;
  permission_sources?: Record<string, string>;
  features: Record<FeatureFlag, boolean> & Partial<Record<string, boolean>>;
}

export interface AuthSessionResponse {
  authenticated: boolean;
  user: AuthUser | null;
}

export interface AuthLoginResponse {
  success: boolean;
  authenticated: boolean;
  next_url: string;
  user: AuthUser;
}

export interface FrontendServer {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string;
  server_type: "ssh";
  status: ServerStatus;
  group_id: number | null;
  group_name: string;
  is_shared: boolean;
  can_edit: boolean;
  share_context_enabled: boolean;
  shared_by_username: string;
  terminal_path: string;
  minimal_terminal_path: string;
  last_connected: string | null;
  sudo_auth_mode?: "none" | "nopasswd" | "stored_password";
  has_saved_sudo_password?: boolean;
  detected_os?: string;
  detected_os_pretty?: string;
  detected_os_meta?: Record<string, unknown>;
}

export interface ServerDetailsResponse {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string;
  server_type: "ssh";
  auth_method: "password" | "key" | "key_password";
  key_path: string;
  tags: string;
  notes: string;
  group_id: number | null;
  is_active: boolean;
  ai_read_only?: boolean;
  sudo_auth_mode?: "none" | "nopasswd" | "stored_password";
  has_saved_sudo_password?: boolean;
  corporate_context?: string;
  network_config?: Record<string, unknown>;
  has_saved_password?: boolean;
  can_view_password?: boolean;
  can_edit?: boolean;
  is_shared_server?: boolean;
  share_context_enabled?: boolean;
  shared_by_username?: string;
}

export type ServerGroupRole = "owner" | "admin" | "member" | "viewer";
export type ServerGroupSubscriptionKind = "follow" | "favorite";

export interface FrontendGroup {
  id: number | null;
  name: string;
  description: string;
  color: string;
  server_count: number;
  role: ServerGroupRole | "";
  can_edit: boolean;
}

export interface FrontendActivity {
  id: number;
  action: string;
  status: "info" | "success" | "error";
  description: string;
  entity_name: string;
  created_at: string | null;
}

export interface FrontendBootstrapResponse {
  success: boolean;
  servers: FrontendServer[];
  groups: FrontendGroup[];
  stats: {
    owned: number;
    shared: number;
    total: number;
  };
  recent_activity: FrontendActivity[];
}

export interface AccessUser {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  is_active: boolean;
  is_superuser?: boolean;
  access_profile?: string;
  groups?: Array<{ id: number; name: string }>;
  effective_permissions?: Record<string, boolean>;
  explicit_permissions?: Record<string, boolean>;
  group_permissions?: Record<string, boolean>;
  group_permission_sources?: Record<string, Array<{ group_id: number; group_name: string; allowed: boolean }>>;
  permission_sources?: Record<string, string>;
}

export interface AccessGroup {
  id: number;
  name: string;
  member_count: number;
  members?: Array<{ id: number; username: string }>;
  explicit_permissions?: Record<string, boolean>;
}

export interface AccessPermission {
  id: number;
  user_id: number;
  username: string;
  feature: string;
  feature_display?: string;
  allowed: boolean;
}

export interface AccessGroupPermission {
  id: number;
  group_id: number;
  group_name: string;
  feature: string;
  feature_display?: string;
  allowed: boolean;
}

export interface SettingsConfig {
  default_provider: string;
  internal_llm_provider: string;
  gemini_enabled: boolean;
  grok_enabled: boolean;
  openai_enabled: boolean;
  fair_enabled: boolean;
  ollama_enabled: boolean;
  ollama_cloud_enabled?: boolean;
  chat_llm_provider: string;
  chat_llm_model: string;
  agent_llm_provider: string;
  agent_llm_model: string;
  orchestrator_llm_provider: string;
  orchestrator_llm_model: string;
  claude_enabled: boolean;
  chat_model_gemini: string;
  chat_model_grok: string;
  chat_model_openai: string;
  chat_model_fair: string;
  chat_model_claude: string;
  chat_model_ollama: string;
  agent_model_fair?: string;
  agent_model_ollama?: string;
  fair_base_url?: string;
  ollama_base_url?: string;
  ollama_runtime_mode?: string;
  ollama_cloud_base_url?: string;
  ollama_think_mode?: string;
  log_terminal_commands: boolean;
  log_ai_assistant: boolean;
  log_agent_runs: boolean;
  log_pipeline_runs: boolean;
  log_auth_events: boolean;
  log_server_changes: boolean;
  log_settings_changes: boolean;
  log_file_operations: boolean;
  log_mcp_calls: boolean;
  log_http_requests: boolean;
  retention_days: number;
  export_format: string;
  openai_reasoning_effort?: string;
  domain_auth_enabled?: boolean;
  domain_auth_header?: string;
  domain_auth_auto_create?: boolean;
  domain_auth_lowercase_usernames?: boolean;
  domain_auth_default_profile?: string;
  [key: string]: string | number | boolean | null | undefined;
}

export interface SettingsConfigResponse {
  success: boolean;
  config: SettingsConfig;
  api_keys?: Record<string, boolean>;
  providers?: Record<string, unknown>;
}

export interface ModelsResponse {
  gemini: string[];
  grok: string[];
  openai: string[];
  fair: string[];
  claude: string[];
  ollama: string[];
  ollama_local?: string[];
  ollama_cloud?: string[];
  current: {
    default_provider: string;
    chat_gemini: string;
    chat_grok: string;
    chat_openai: string;
    chat_fair?: string;
    chat_claude: string;
    chat_ollama?: string;
    agent_model_fair?: string;
    agent_model_ollama?: string;
    ollama_runtime_mode?: string;
    ollama_think_mode?: string;
  };
}

export interface ActivityLogEvent {
  id: number;
  created_at: string;
  timestamp?: string;
  user_id?: number | null;
  username: string;
  category: string;
  action: string;
  status: string;
  description: string;
  entity_type?: string;
  entity_id?: number | string | null;
  entity_name: string;
  ip_address?: string;
  user_agent?: string;
  metadata?: Record<string, unknown>;
}

export interface ActivityLogsResponse {
  success: boolean;
  events: ActivityLogEvent[];
  summary: {
    total_events: number;
    total_users: number;
    login_count?: number;
    assistant_requests?: number;
    server_connections?: number;
    server_changes?: number;
  };
}

function normalizeWsOrigin(rawValue: string): string {
  const raw = (rawValue || "").trim().replace(/\/$/, "");
  if (!raw) return "";
  if (raw.startsWith("ws://") || raw.startsWith("wss://")) return raw;
  if (raw.startsWith("http://")) return `ws://${raw.slice("http://".length)}`;
  if (raw.startsWith("https://")) return `wss://${raw.slice("https://".length)}`;
  const proto = window.location.protocol === "https:" ? "wss://" : "ws://";
  return `${proto}${raw}`;
}

function buildWsBase(): string {
  const explicitWs = normalizeWsOrigin(import.meta.env.VITE_DJANGO_WS_URL || "");
  if (explicitWs) {
    return explicitWs;
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = import.meta.env.VITE_WS_HOST || window.location.host;
  return `${proto}//${host}`;
}

export function getWsUrl(serverId: number | string, wsToken?: string): string {
  const base = `${buildWsBase()}/ws/servers/${serverId}/terminal/`;
  if (wsToken) {
    return `${base}?ws_token=${encodeURIComponent(wsToken)}`;
  }
  return base;
}

export function getStudioPipelineRunWsUrl(runId: number | string): string {
  return `${buildWsBase()}/ws/studio/pipeline-runs/${runId}/live/`;
}

export function getMarsRunWsUrl(runId: number | string): string {
  return `${buildWsBase()}/ws/mars/runs/${runId}/live/`;
}

/** Fetch a short-lived WS auth token from Django (solves Vite proxy cookie issue). */
export async function fetchWsToken(): Promise<string | null> {
  try {
    const data = await apiFetch<{ token: string }>("/api/auth/ws-token/");
    return data.token ?? null;
  } catch {
    return null;
  }
}

export function backendPath(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (BACKEND_ORIGIN) return `${BACKEND_ORIGIN}${normalized}`;
  return normalized;
}

export function getRdpPath(serverId: number | string): string {
  return backendPath(`/servers/${serverId}/terminal/`);
}

export async function fetchAuthSession(): Promise<AuthSessionResponse> {
  if (isDemoMode()) return DEMO_SESSION;
  try {
    return await apiFetch<AuthSessionResponse>("/api/auth/session/");
  } catch {
    if (canUseDemoMode() && enableDemoMode()) {
      return DEMO_SESSION;
    }
    return { authenticated: false, user: null };
  }
}

export async function authLogin(username: string, password: string, authMode: "auto" | "local" = "auto") {
  return apiFetch<AuthLoginResponse>("/api/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password, auth_mode: authMode }),
    timeoutMs: 10_000,
  });
}

export async function authLogout() {
  return apiFetch<{ success: boolean }>("/api/auth/logout/", { method: "POST" });
}

export async function fetchFrontendBootstrap() {
  return apiFetch<FrontendBootstrapResponse>("/servers/api/frontend/bootstrap/");
}

export async function buildBinaryRequestHeaders(method = "POST"): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};
  if (isMutationRequest(method)) {
    const csrfToken = await ensureCsrfToken();
    if (csrfToken) headers["X-CSRFToken"] = csrfToken;
  }
  return headers;
}

export async function createServer(payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; server_id: number; message: string }>("/servers/api/create/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateServer(serverId: number, payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; message: string }>(`/servers/api/${serverId}/update/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchServerDetails(serverId: number) {
  return apiFetch<ServerDetailsResponse>(`/servers/api/${serverId}/get/`);
}

export async function executeServerCommand(serverId: number, command: string, password = "") {
  return apiFetch<{
    success: boolean;
    output?: {
      stdout?: string;
      stderr?: string;
      exit_code?: number;
      [key: string]: unknown;
    };
    error?: string;
  }>(`/servers/api/${serverId}/execute/`, {
    method: "POST",
    body: JSON.stringify({ command, password }),
  });
}

export async function revealServerPassword(serverId: number, masterPassword = "") {
  return apiFetch<{ success: boolean; password?: string; error?: string }>(`/servers/api/${serverId}/reveal-password/`, {
    method: "POST",
    body: JSON.stringify(masterPassword ? { master_password: masterPassword } : {}),
  });
}

export async function listServerShares(serverId: number) {
  return apiFetch<{
    success: boolean;
    shares: Array<{
      id: number;
      user_id: number;
      username: string;
      email: string;
      share_context: boolean;
      expires_at: string | null;
      created_at: string | null;
      is_active: boolean;
    }>;
  }>(`/servers/api/${serverId}/shares/`);
}

export async function createServerShare(
  serverId: number,
  payload: { user: string; share_context?: boolean; expires_at?: string | null },
) {
  return apiFetch<{ success: boolean }>(`/servers/api/${serverId}/share/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function revokeServerShare(serverId: number, shareId: number) {
  return apiFetch<{ success: boolean }>(`/servers/api/${serverId}/shares/${shareId}/revoke/`, { method: "POST" });
}

export async function createServerGroup(payload: {
  name: string;
  description?: string;
  color?: string;
  tag_ids?: number[];
}) {
  return apiFetch<{ success: boolean; group_id?: number; error?: string }>("/servers/api/groups/create/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateServerGroup(
  groupId: number,
  payload: { name?: string; description?: string; color?: string; tag_ids?: number[] },
) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/groups/${groupId}/update/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteServerGroup(groupId: number) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/groups/${groupId}/delete/`, {
    method: "POST",
  });
}

export async function addServerGroupMember(
  groupId: number,
  payload: { user: string; role?: ServerGroupRole },
) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/groups/${groupId}/add-member/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function removeServerGroupMember(groupId: number, userId: number) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/groups/${groupId}/remove-member/`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export async function subscribeServerGroup(groupId: number, kind: ServerGroupSubscriptionKind) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/groups/${groupId}/subscribe/`, {
    method: "POST",
    body: JSON.stringify({ kind }),
  });
}

export async function bulkUpdateServers(payload: {
  server_ids: number[];
  group_id?: number | null;
  tags?: string;
  is_active?: boolean;
}) {
  return apiFetch<{ success: boolean; updated_count?: number; error?: string }>("/servers/api/bulk-update/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function setMasterPassword(masterPassword: string) {
  return apiFetch<{ success: boolean; error?: string }>("/servers/api/master-password/set/", {
    method: "POST",
    body: JSON.stringify({ master_password: masterPassword }),
  });
}

export async function getMasterPasswordStatus() {
  return apiFetch<{ has_master_password: boolean }>("/servers/api/master-password/check/");
}

export async function clearMasterPassword() {
  return apiFetch<{ success: boolean }>("/servers/api/master-password/clear/");
}

export async function testServer(serverId: number, payload: Record<string, unknown> = {}) {
  return apiFetch<{ success: boolean; message?: string; error?: string }>(`/servers/api/${serverId}/test/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteServer(serverId: number) {
  return apiFetch<{ success: boolean; message?: string }>(`/servers/api/${serverId}/delete/`, { method: "POST" });
}

export async function fetchSettings() {
  return apiFetch<SettingsConfigResponse>("/api/settings/");
}

export async function saveSettings(config: Record<string, unknown>) {
  return apiFetch<{ success: boolean; message?: string }>("/api/settings/", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export async function fetchModels() {
  return apiFetch<ModelsResponse>("/api/models/");
}

export async function refreshModels(provider: "gemini" | "grok" | "openai" | "fair" | "claude" | "ollama") {
  return apiFetch<{ success: boolean; provider: string; models: string[]; count: number }>("/api/models/refresh/", {
    method: "POST",
    body: JSON.stringify({ provider }),
  });
}

export async function fetchSettingsActivity(limit = 30, days = 14) {
  return apiFetch<ActivityLogsResponse>(`/api/settings/activity/?limit=${limit}&days=${days}`);
}

export async function fetchAccessUsers() {
  return apiFetch<{ users: AccessUser[]; features?: Array<{ value: string; label: string }> }>("/api/access/users/");
}

export async function createAccessUser(payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; user: AccessUser }>("/api/access/users/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAccessUser(userId: number, payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; user: AccessUser }>(`/api/access/users/${userId}/`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteAccessUser(userId: number) {
  return apiFetch<{ success: boolean; message: string }>(`/api/access/users/${userId}/`, { method: "DELETE" });
}

export async function setAccessUserPassword(userId: number, password: string) {
  return apiFetch<{ success: boolean; message: string }>(`/api/access/users/${userId}/password/`, {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export async function fetchAccessGroups() {
  return apiFetch<{ groups: AccessGroup[]; features?: Array<{ value: string; label: string }> }>("/api/access/groups/");
}

export async function createAccessGroup(payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; group: AccessGroup }>("/api/access/groups/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAccessGroup(groupId: number, payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; group: AccessGroup }>(`/api/access/groups/${groupId}/`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteAccessGroup(groupId: number) {
  return apiFetch<{ success: boolean; message: string }>(`/api/access/groups/${groupId}/`, { method: "DELETE" });
}

export async function fetchAccessPermissions() {
  return apiFetch<{
    permissions: AccessPermission[];
    group_permissions?: AccessGroupPermission[];
    features: Array<{ value: string; label: string }>;
  }>(
    "/api/access/permissions/",
  );
}

export async function upsertAccessPermission(payload: { user_id: number; feature: string; allowed: boolean }) {
  return apiFetch<{ success: boolean; permission: AccessPermission }>("/api/access/permissions/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAccessPermission(permId: number, allowed: boolean) {
  return apiFetch<{ success: boolean; permission: AccessPermission }>(`/api/access/permissions/${permId}/`, {
    method: "PUT",
    body: JSON.stringify({ allowed }),
  });
}

export async function deleteAccessPermission(permId: number) {
  return apiFetch<{ success: boolean; message: string }>(`/api/access/permissions/${permId}/`, {
    method: "DELETE",
  });
}

export async function fetchAccessGroupPermissions() {
  return apiFetch<{ permissions: AccessGroupPermission[]; features: Array<{ value: string; label: string }> }>(
    "/api/access/group-permissions/",
  );
}

export async function upsertAccessGroupPermission(payload: { group_id: number; feature: string; allowed: boolean }) {
  return apiFetch<{ success: boolean; permission: AccessGroupPermission }>("/api/access/group-permissions/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAccessGroupPermission(permId: number, allowed: boolean) {
  return apiFetch<{ success: boolean; permission: AccessGroupPermission }>(`/api/access/group-permissions/${permId}/`, {
    method: "PUT",
    body: JSON.stringify({ allowed }),
  });
}

export async function deleteAccessGroupPermission(permId: number) {
  return apiFetch<{ success: boolean; message: string }>(`/api/access/group-permissions/${permId}/`, {
    method: "DELETE",
  });
}

export type WatcherDraftSeverity = "info" | "warning" | "critical";
export type WatcherDraftStatus = "open" | "acknowledged" | "resolved" | "suppressed";

export interface WatcherDraftItem {
  id: number;
  server_id: number;
  server_name: string;
  severity: WatcherDraftSeverity;
  recommended_role: string;
  objective: string;
  reasons: string[];
  memory_excerpt: string[];
  status: WatcherDraftStatus;
  acknowledged_at: string | null;
  acknowledged_by: string;
  resolved_at: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  metadata: Record<string, unknown>;
}

export interface WatcherDraftSummary {
  open: number;
  acknowledged: number;
  resolved: number;
  suppressed: number;
  total: number;
}

export interface WatcherScanSummary {
  scanned_servers: number;
  critical: number;
  warning: number;
  drafts: number;
}

export interface WatcherPersistedStats {
  created: number;
  updated: number;
  reopened: number;
  resolved: number;
}

export interface WatcherScanDraft {
  server_id: number;
  server_name: string;
  severity: WatcherDraftSeverity;
  recommended_role: string;
  objective: string;
  reasons: string[];
  memory_excerpt: string[];
}

export interface WatcherDraftsResponse {
  success: boolean;
  summary: WatcherDraftSummary;
  drafts: WatcherDraftItem[];
}

export interface WatcherScanResponse {
  success: boolean;
  generated_at: string;
  summary: WatcherScanSummary;
  scanned_server_ids: number[];
  requested_server_ids: number[];
  persisted_scan: boolean;
  persisted?: WatcherPersistedStats;
  drafts: WatcherScanDraft[];
}

export async function fetchWatcherDrafts(options?: {
  statuses?: WatcherDraftStatus[];
  serverId?: number;
  limit?: number;
}) {
  const params = new URLSearchParams();
  for (const status of options?.statuses || []) {
    params.append("status", status);
  }
  if (options?.serverId) {
    params.set("server_id", String(options.serverId));
  }
  if (options?.limit) {
    params.set("limit", String(options.limit));
  }
  const query = params.toString();
  return apiFetch<WatcherDraftsResponse>(`/servers/api/watchers/drafts/${query ? `?${query}` : ""}`);
}

export async function scanWatcherDrafts(payload?: {
  persist?: boolean;
  server_ids?: number[];
  limit?: number;
}) {
  return apiFetch<WatcherScanResponse>("/servers/api/watchers/scan/", {
    method: "POST",
    body: JSON.stringify(payload || { persist: true }),
  });
}

export async function acknowledgeWatcherDraft(draftId: number) {
  return apiFetch<{ success: boolean; draft: WatcherDraftItem }>(`/servers/api/watchers/drafts/${draftId}/ack/`, {
    method: "POST",
  });
}

export async function launchWatcherDraft(draftId: number) {
  return apiFetch<{
    success: boolean;
    draft: WatcherDraftItem;
    agent_id: number;
    run_id: number;
    status: string;
  }>(`/servers/api/watchers/drafts/${draftId}/launch/`, {
    method: "POST",
  });
}

// =============================================================================
// Studio API
// =============================================================================

export interface PipelineLastRun {
  id: number;
  status: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface PipelineTriggerSummary {
  active_total: number;
  active_manual: number;
  active_webhook: number;
  active_schedule: number;
  active_monitoring?: number;
  last_triggered_at: string | null;
}

export interface PipelineListItem {
  id: number;
  name: string;
  description: string;
  icon: string;
  tags: string[];
  is_shared: boolean;
  is_template: boolean;
  graph_version: number;
  node_count: number;
  created_at: string;
  updated_at: string;
  trigger_summary?: PipelineTriggerSummary;
  last_run: PipelineLastRun | null;
  owner?: StudioSharedUser | null;
  owner_username?: string;
  is_owner?: boolean;
  can_edit?: boolean;
  access_mode?: StudioAccessMode;
}

export interface PipelineNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: Record<string, unknown>;
}

export interface PipelineEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  label?: string;
}

export interface PipelineDetail extends PipelineListItem {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  triggers?: PipelineTrigger[];
}

export interface NodeState {
  status: string;
  output?: string;
  error?: string;
  agent_run_id?: number;
  started_at?: string;
  finished_at?: string;
  passed?: boolean;
  routing_ports?: string[];
  decision?: string;
}

export interface PipelineRun {
  id: number;
  pipeline_id: number;
  pipeline_name: string;
  status: string;
  node_states: Record<string, NodeState>;
  nodes_snapshot: PipelineNode[];
  context: Record<string, unknown>;
  summary: string;
  error: string;
  duration_seconds: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  triggered_by: string | null;
  trigger_id: number | null;
  entry_node_id: string;
  trigger_type: string;
  trigger_name: string;
  trigger_node_id: string;
}

export interface PipelineRunValidation {
  ok: boolean;
  validation: {
    ok: boolean;
    errors: string[];
    warnings?: string[];
  };
  risk?: {
    level: "safe" | "dangerous" | string;
    items: Array<{
      node_id?: string;
      node_label?: string;
      stage?: string;
      command?: string;
      level?: string;
      categories?: string[];
      matched_patterns?: string[];
      reasons?: string[];
    }>;
  };
  dry_run?: {
    ok: boolean;
    executed: boolean;
    mode: string;
    checks: string[];
    message: string;
  };
  entry_node_id?: string;
  trigger_type?: string;
  would_create_run?: boolean;
}

export type StudioAccessMode = "owner" | "shared" | "admin";

export interface StudioSharedUser {
  id: number;
  username: string;
  email?: string;
}

export interface StudioAccessMetadata {
  owner?: StudioSharedUser | null;
  owner_username?: string;
  is_owner?: boolean;
  can_edit?: boolean;
  can_share?: boolean;
  is_shared?: boolean;
  shared_user_ids?: number[];
  shared_users?: StudioSharedUser[];
  access_mode?: StudioAccessMode;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AgentConfig extends StudioAccessMetadata {
  id: number;
  name: string;
  description: string;
  icon: string;
  system_prompt: string;
  instructions: string;
  model: string;
  max_iterations: number;
  allowed_tools: string[];
  sudo_policy: "disabled" | "ask" | "approved";
  skill_slugs: string[];
  skills: StudioSkill[];
  skill_errors?: string[];
  mcp_servers: Array<{ id: number; name: string; transport: string }>;
  server_scope: Array<{ id: number; name: string }>;
}

export interface StudioSkill extends StudioAccessMetadata {
  slug: string;
  name: string;
  description: string;
  tags: string[];
  service: string;
  category: string;
  safety_level: string;
  ui_hint: string;
  guardrail_summary: string[];
  recommended_tools: string[];
  runtime_enforced: boolean;
  path: string;
}

export interface StudioSkillDetail extends StudioSkill {
  runtime_policy: Record<string, unknown>;
  metadata: Record<string, unknown>;
  content: string;
}

export interface StudioSkillTemplate {
  slug: string;
  name: string;
  description: string;
  summary: string;
  defaults: {
    name?: string;
    description?: string;
    service?: string;
    category?: string;
    safety_level?: string;
    ui_hint?: string;
    tags?: string[];
    guardrail_summary?: string[];
    recommended_tools?: string[];
    runtime_policy?: Record<string, unknown>;
  };
}

export interface StudioSkillValidationResult {
  slug: string;
  path: string;
  errors: string[];
  warnings: string[];
  is_valid: boolean;
}

export interface StudioSkillValidationResponse {
  results: StudioSkillValidationResult[];
  summary: {
    skills: number;
    errors: number;
    warnings: number;
    is_valid: boolean;
    strict: boolean;
  };
}

export interface StudioSkillScaffoldPayload {
  template_slug?: string;
  name: string;
  description: string;
  slug?: string;
  service?: string;
  category?: string;
  safety_level?: string;
  ui_hint?: string;
  tags?: string[];
  guardrail_summary?: string[];
  recommended_tools?: string[];
  runtime_policy?: Record<string, unknown>;
  with_scripts?: boolean;
  with_references?: boolean;
  with_assets?: boolean;
  force?: boolean;
  is_shared?: boolean;
  shared_user_ids?: number[];
}

export interface StudioSkillScaffoldResponse {
  ok: boolean;
  skill: StudioSkillDetail;
  validation: StudioSkillValidationResult;
}

export interface StudioSkillWorkspaceFile {
  path: string;
  name: string;
  kind: "skill" | "reference" | "script" | "asset" | "file";
  language: string;
  size: number;
  editable: boolean;
}

export interface StudioSkillWorkspaceFileDetail extends StudioSkillWorkspaceFile {
  content: string;
}

export interface StudioSkillWorkspace {
  skill: StudioSkillDetail;
  files: StudioSkillWorkspaceFile[];
  validation: StudioSkillValidationResult;
}

export interface StudioSkillWorkspaceMutationResponse {
  ok: boolean;
  file?: StudioSkillWorkspaceFileDetail;
  validation: StudioSkillValidationResult;
}

export interface MCPServer extends StudioAccessMetadata {
  id: number;
  name: string;
  description: string;
  transport: "stdio" | "sse";
  command: string;
  args: string[];
  env: Record<string, string>;
  secret_env_keys?: string[];
  url: string;
  is_shared: boolean;
  last_test_ok: boolean | null;
  last_test_at: string | null;
  last_test_error: string;
}

export interface MCPServerTool {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
}

export interface MCPTemplate {
  slug: string;
  name: string;
  description: string;
  transport: "stdio" | "sse";
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  icon?: string;
}

export interface MCPServerInspection {
  server: {
    name: string;
    transport: string;
    protocol_version: string;
    server_info: Record<string, unknown>;
    capabilities: Record<string, unknown>;
  };
  tools: MCPServerTool[];
}

export type JsonSchema = Record<string, unknown>;

export interface StudioCapabilityNode {
  type: string;
  category: string;
  purpose: string;
  source_handles: string[];
  risk_level: string;
  mutates_state: boolean;
  supports_dry_run: boolean;
  requires_approval_by_default: boolean;
  recommended_verification: string[];
  tags: string[];
  input_schema: JsonSchema;
  output_schema: JsonSchema;
  metadata?: Record<string, unknown>;
}

export interface StudioNodeManifestRegistry {
  version: number;
  count: number;
  nodes: StudioCapabilityNode[];
}

export interface StudioCapabilityTaskFamily {
  slug: string;
  name: string;
  description: string;
  readiness: "ready" | "partial" | "missing";
  missing: string[];
  preferred_nodes: string[];
  required_capabilities: string[];
  matching_mcp_servers: Array<{ id: number; name: string; transport: string; last_test_ok: boolean | null }>;
  matching_skills: Array<{ slug: string; name: string; service: string; safety_level: string }>;
  pilot_prompt: string;
  capability_packs?: Array<{
    slug: string;
    name: string;
    service: string;
    mcp_server_name: string;
    tool_names: string[];
    skill_slugs: string[];
  }>;
}

export interface StudioCapabilityPackTool {
  pack_slug: string;
  pack_name: string;
  task_family: string;
  service: string;
  mcp_server_name: string;
  tool_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  permission_mode: string;
  risk_level: string;
  operation_kind: string;
  mutates_state: boolean;
  requires_approval: boolean;
  skill_slugs: string[];
  policy_tags: string[];
}

export interface StudioCapabilityPack {
  slug: string;
  name: string;
  task_family: string;
  service: string;
  mcp_server_name: string;
  skill_slugs: string[];
  tools: StudioCapabilityPackTool[];
}

export interface StudioCapabilityRegistry {
  strategy: {
    mode: string;
    service_specific_work: string;
    default_execution_node: string;
    approval_node: string;
    verification_nodes: string[];
  };
  nodes: StudioCapabilityNode[];
  capability_packs: StudioCapabilityPack[];
  resources: {
    mcp_servers: Array<{ id: number; name: string; description: string; transport: string; last_test_ok: boolean | null }>;
    skills: Array<{ slug: string; name: string; description: string; service: string; category: string; safety_level: string }>;
    server_count: number | null;
  };
  task_families: StudioCapabilityTaskFamily[];
}

export interface PipelineTrigger {
  id: number;
  pipeline_id: number;
  node_id: string;
  name: string;
  trigger_type: "manual" | "webhook" | "schedule" | "monitoring";
  is_active: boolean;
  webhook_token: string;
  webhook_url: string;
  cron_expression: string;
  webhook_payload_map: Record<string, unknown>;
  monitoring_filters?: Record<string, unknown>;
  last_triggered_at: string | null;
}

// Pipelines
export const studioPipelines = {
  list: (q?: string) => apiFetch<PipelineListItem[]>(`/api/studio/pipelines/${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  get: (id: number) => apiFetch<PipelineDetail>(`/api/studio/pipelines/${id}/`),
  create: (data: Partial<PipelineDetail>) => apiFetch<PipelineDetail>("/api/studio/pipelines/", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: Partial<PipelineDetail>) => apiFetch<PipelineDetail>(`/api/studio/pipelines/${id}/`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: number) => apiFetch<{ ok: boolean }>(`/api/studio/pipelines/${id}/`, { method: "DELETE" }),
  run: (id: number, context?: Record<string, unknown>, entryNodeId?: string) =>
    apiFetch<PipelineRun>(`/api/studio/pipelines/${id}/run/`, {
      method: "POST",
      body: JSON.stringify({
        context: context || {},
        entry_node_id: entryNodeId || undefined,
      }),
    }),
  validateRun: (id: number, context?: Record<string, unknown>, entryNodeId?: string) =>
    apiFetch<PipelineRunValidation>(`/api/studio/pipelines/${id}/run/`, {
      method: "POST",
      body: JSON.stringify({
        context: context || {},
        entry_node_id: entryNodeId || undefined,
        validate_only: true,
        dry_run: true,
      }),
    }),
  clone: (id: number) => apiFetch<PipelineDetail>(`/api/studio/pipelines/${id}/clone/`, { method: "POST" }),
  runs: (id: number) => apiFetch<PipelineRun[]>(`/api/studio/pipelines/${id}/runs/`),
  assistant: (data: StudioPipelineAssistantPayload) =>
    apiFetch<StudioPipelineAssistantResponse>("/api/studio/pipelines/assistant/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// Runs
export const studioRuns = {
  list: () => apiFetch<PipelineRun[]>("/api/studio/runs/"),
  get: (id: number) => apiFetch<PipelineRun>(`/api/studio/runs/${id}/`),
  stop: (id: number) => apiFetch<{ ok: boolean }>(`/api/studio/runs/${id}/stop/`, { method: "POST" }),
};

// Agent Configs
export const studioAgents = {
  list: () => apiFetch<AgentConfig[]>("/api/studio/agents/"),
  get: (id: number) => apiFetch<AgentConfig>(`/api/studio/agents/${id}/`),
  create: (data: Partial<AgentConfig>) => apiFetch<AgentConfig>("/api/studio/agents/", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: Partial<AgentConfig>) => apiFetch<AgentConfig>(`/api/studio/agents/${id}/`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: number) => apiFetch<{ ok: boolean }>(`/api/studio/agents/${id}/`, { method: "DELETE" }),
};

export const studioSkills = {
  list: () => apiFetch<StudioSkill[]>("/api/studio/skills/"),
  get: (slug: string) => apiFetch<StudioSkillDetail>(`/api/studio/skills/${encodeURIComponent(slug)}/`),
  update: (slug: string, data: Partial<StudioSkillDetail>) =>
    apiFetch<StudioSkillDetail>(`/api/studio/skills/${encodeURIComponent(slug)}/`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  templates: () => apiFetch<StudioSkillTemplate[]>("/api/studio/skills/templates/"),
  scaffold: (data: StudioSkillScaffoldPayload) =>
    apiFetch<StudioSkillScaffoldResponse>("/api/studio/skills/scaffold/", { method: "POST", body: JSON.stringify(data) }),
  validate: (slugs?: string[], strict = false) =>
    apiFetch<StudioSkillValidationResponse>("/api/studio/skills/validate/", {
      method: "POST",
      body: JSON.stringify({ slugs: slugs || [], strict }),
    }),
  workspace: (slug: string) => apiFetch<StudioSkillWorkspace>(`/api/studio/skills/${encodeURIComponent(slug)}/workspace/`),
  readFile: (slug: string, path: string) =>
    apiFetch<StudioSkillWorkspaceFileDetail>(`/api/studio/skills/${encodeURIComponent(slug)}/workspace/file/?path=${encodeURIComponent(path)}`),
  createFile: (slug: string, data: { path: string; content: string }) =>
    apiFetch<StudioSkillWorkspaceMutationResponse>(`/api/studio/skills/${encodeURIComponent(slug)}/workspace/file/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateFile: (slug: string, data: { path: string; content: string }) =>
    apiFetch<StudioSkillWorkspaceMutationResponse>(`/api/studio/skills/${encodeURIComponent(slug)}/workspace/file/`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteFile: (slug: string, path: string) =>
    apiFetch<StudioSkillWorkspaceMutationResponse>(`/api/studio/skills/${encodeURIComponent(slug)}/workspace/file/`, {
      method: "DELETE",
      body: JSON.stringify({ path }),
    }),
};

// MCP
export const studioMCP = {
  list: () => apiFetch<MCPServer[]>("/api/studio/mcp/"),
  get: (id: number) => apiFetch<MCPServer>(`/api/studio/mcp/${id}/`),
  create: (data: Partial<MCPServer>) => apiFetch<MCPServer>("/api/studio/mcp/", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: Partial<MCPServer>) => apiFetch<MCPServer>(`/api/studio/mcp/${id}/`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: number) => apiFetch<{ ok: boolean }>(`/api/studio/mcp/${id}/`, { method: "DELETE" }),
  test: (id: number) => apiFetch<{ ok: boolean; error: string | null }>(`/api/studio/mcp/${id}/test/`, { method: "POST" }),
  templates: () => apiFetch<MCPTemplate[]>("/api/studio/mcp/templates/"),
  tools: (id: number) => apiFetch<MCPServerInspection>(`/api/studio/mcp/${id}/tools/`),
};

export const studioCapabilities = {
  get: () => apiFetch<StudioCapabilityRegistry>("/api/studio/capabilities/"),
};

export const studioNodeManifests = {
  get: () => apiFetch<StudioNodeManifestRegistry>("/api/studio/node-manifests/"),
};

export const studioShareUsers = {
  list: () => apiFetch<StudioSharedUser[]>("/api/studio/share-users/"),
};

// Triggers
export const studioTriggers = {
  list: (pipelineId?: number) => apiFetch<PipelineTrigger[]>(`/api/studio/triggers/${pipelineId ? `?pipeline_id=${pipelineId}` : ""}`),
  create: (data: Partial<PipelineTrigger>) => apiFetch<PipelineTrigger>("/api/studio/triggers/", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: Partial<PipelineTrigger>) => apiFetch<PipelineTrigger>(`/api/studio/triggers/${id}/`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: number) => apiFetch<{ ok: boolean }>(`/api/studio/triggers/${id}/`, { method: "DELETE" }),
};

// Templates
export const studioTemplates = {
  list: () => apiFetch<Array<Record<string, unknown>>>("/api/studio/templates/"),
  use: (slug: string) => apiFetch<PipelineDetail>(`/api/studio/templates/${slug}/use/`, { method: "POST" }),
};

// Servers (for dropdowns in node config)
export const studioServers = {
  list: () => apiFetch<Array<{ id: number; name: string; host: string }>>("/api/studio/servers/"),
};

// Notification settings
export interface NotificationConfig {
  telegram_bot_token: string;
  telegram_chat_id: string;
  notify_email: string;
  smtp_host: string;
  smtp_port: string;
  smtp_user: string;
  smtp_password: string;
  from_email: string;
  site_url: string;
}

export const studioNotifications = {
  get: () => apiFetch<NotificationConfig>("/api/studio/notifications/"),
  save: (data: Partial<NotificationConfig>) =>
    apiFetch<{ ok: boolean; saved: string[] }>("/api/studio/notifications/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  testTelegram: () =>
    apiFetch<{ ok: boolean; message: string }>("/api/studio/notifications/test-telegram/", { method: "POST" }),
  testEmail: () =>
    apiFetch<{ ok: boolean; message: string }>("/api/studio/notifications/test-email/", { method: "POST" }),
};
