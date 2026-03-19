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

const API_BASE = import.meta.env.VITE_API_BASE || "";
const BACKEND_ORIGIN = (
  import.meta.env.VITE_BACKEND_ORIGIN ||
  (window.location.port === "8080" ? "http://127.0.0.1:9000" : "")
).replace(/\/$/, "");
let csrfTokenCache: string | null = null;
let csrfTokenRequest: Promise<string | null> | null = null;

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? match[2] : null;
}

function isMutationRequest(method?: string): boolean {
  const normalized = (method || "GET").toUpperCase();
  return !["GET", "HEAD", "OPTIONS", "TRACE"].includes(normalized);
}

async function ensureCsrfToken(): Promise<string | null> {
  const cookieToken = getCookie("csrftoken");
  if (cookieToken) {
    csrfTokenCache = cookieToken;
    return cookieToken;
  }

  if (csrfTokenCache) {
    return csrfTokenCache;
  }

  if (isDemoMode()) return null;

  if (!csrfTokenRequest) {
    csrfTokenRequest = fetch(`${API_BASE}/api/auth/csrf/`, {
      credentials: "include",
    })
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
  if (enableDemoMode()) {
    return demoFallback<T>(path, options);
  }
  throw new Error(errorMessage);
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  // In demo mode, return mock data for known paths
  if (isDemoMode()) {
    return demoFallback<T>(path, options);
  }

  let response: Response;
  try {
    const csrfToken = isMutationRequest(options.method) ? await ensureCsrfToken() : getCookie("csrftoken");
    response = await fetch(`${API_BASE}${path}`, {
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
        ...((options.headers as Record<string, string>) || {}),
      },
      ...options,
    });
  } catch {
    // Network error — backend unreachable
    return fallbackToDemoOrThrow<T>(path, options, "Backend unavailable");
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

  // Settings page
  if (path.includes("/api/settings/activity")) return DEMO_ACTIVITY_LOGS as T;
  if (path.includes("/api/settings")) return DEMO_SETTINGS as T;
  if (path.includes("/api/models/refresh")) return { success: true, provider: "gemini", models: ["gemini-2.0-flash"], count: 1 } as T;
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

  // Agents
  if (path.includes("/servers/api/agents/dashboard")) return { success: true, active: [], recent: [] } as T;
  if (path.includes("/servers/api/agents/templates")) return { success: true, templates: [] } as T;
  if (path.includes("/servers/api/agents/runs")) return { success: true, runs: [] } as T;
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
        modified_at: Math.floor(Date.now() / 1000) - 86400,
      },
    ],
  } as T;
  if (path.includes("/servers/api/global-context")) return { rules: "", forbidden_commands: [], required_checks: [], environment_vars: {} } as T;
  if (path.includes("/servers/api/master-password")) return { has_master_password: false, success: true } as T;
  if (path.includes("/knowledge")) return { success: true, items: [], categories: [] } as T;
  if (path.includes("/shares")) return { success: true, shares: [] } as T;

  if (path.includes("/api/health")) return { status: "ok" } as T;
  if (path.includes("/api/access/users")) return { success: true, users: [] } as T;
  if (path.includes("/api/access/groups")) return { success: true, groups: [] } as T;
  if (path.includes("/api/access/permissions")) return { success: true, permissions: [] } as T;
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

  // Generic fallback
  return demoSuccess() as T;
}

export type ServerStatus = "online" | "offline" | "unknown";

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  features: {
    servers: boolean;
    dashboard: boolean;
    agents: boolean;
    studio: boolean;
    settings: boolean;
    orchestrator: boolean;
  };
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
  server_type: "ssh" | "rdp";
  rdp: boolean;
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
}

export interface ServerDetailsResponse {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string;
  server_type: "ssh" | "rdp";
  auth_method: "password" | "key" | "key_password";
  key_path: string;
  tags: string;
  notes: string;
  group_id: number | null;
  is_active: boolean;
  corporate_context?: string;
  network_config?: Record<string, unknown>;
  has_saved_password?: boolean;
  can_view_password?: boolean;
  can_edit?: boolean;
  is_shared_server?: boolean;
  share_context_enabled?: boolean;
  shared_by_username?: string;
}

export interface SftpEntry {
  name: string;
  path: string;
  kind: "file" | "dir" | "symlink";
  is_dir: boolean;
  is_symlink: boolean;
  size: number;
  permissions: string;
  modified_at: number;
}

export interface SftpListResponse {
  success: boolean;
  path: string;
  home_path: string;
  parent_path: string | null;
  entries: SftpEntry[];
}

export interface SftpMutationResponse {
  success: boolean;
  path: string;
  entry?: SftpEntry;
  entries?: SftpEntry[];
  deleted_path?: string;
  error?: string;
}

export interface SftpTextFile {
  path: string;
  filename: string;
  size: number;
  encoding: string;
  content: string;
}

export interface SftpTextFileResponse {
  success: boolean;
  file: SftpTextFile;
}

export interface LinuxUiCapabilities {
  hostname: string;
  current_user: string;
  os_name: string;
  os_id: string;
  kernel: string;
  is_systemd: boolean;
  package_manager: "apt" | "dnf" | "yum" | null;
  commands: {
    systemctl: boolean;
    journalctl: boolean;
    docker: boolean;
    ss: boolean;
    ip: boolean;
    apt: boolean;
    dnf: boolean;
    yum: boolean;
    python3: boolean;
    bash: boolean;
    sh: boolean;
  };
  available_apps: {
    overview: boolean;
    files: boolean;
    terminal: boolean;
    ai: boolean;
    services: boolean;
    logs: boolean;
    processes: boolean;
    disk: boolean;
    network: boolean;
    docker: boolean;
    packages: boolean;
  };
}

export interface LinuxUiOverview {
  hostname: string;
  current_user: string;
  home_path: string;
  cwd: string;
  os_name: string;
  kernel: string;
  uptime_seconds: number | null;
  process_count: number | null;
  load: {
    one: number | null;
    five: number | null;
    fifteen: number | null;
  };
  memory: {
    total_mb: number | null;
    used_mb: number | null;
    percent: number | null;
  };
  disk: {
    mount: string;
    total_gb: number | null;
    used_gb: number | null;
    percent: number | null;
  };
}

export interface LinuxUiCapabilitiesResponse {
  success: boolean;
  observed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  capabilities: LinuxUiCapabilities;
}

export interface LinuxUiOverviewResponse {
  success: boolean;
  observed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  overview: LinuxUiOverview;
}

export type LinuxUiServiceHealth = "active" | "failed" | "inactive" | "activating" | "deactivating" | "other";
export type LinuxUiServiceAction = "start" | "stop" | "restart" | "reload";

export interface LinuxUiServiceItem {
  unit: string;
  name: string;
  load: string;
  active: string;
  sub: string;
  description: string;
  health: LinuxUiServiceHealth;
  is_active: boolean;
  is_failed: boolean;
}

export interface LinuxUiServicesSummary {
  total: number;
  active: number;
  failed: number;
  inactive: number;
  other: number;
}

export interface LinuxUiServicesResponse {
  success: boolean;
  observed_at: string;
  limit: number;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  services: LinuxUiServiceItem[];
  summary: LinuxUiServicesSummary;
}

export interface LinuxUiServiceLogsPayload {
  service: string;
  lines: number;
  source: "journalctl" | "systemctl-status";
  content: string;
}

export interface LinuxUiServiceLogsResponse {
  success: boolean;
  observed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  service_logs: LinuxUiServiceLogsPayload;
}

export interface LinuxUiServiceActionPayload {
  service: string;
  action: LinuxUiServiceAction;
}

export interface LinuxUiServiceActionResult {
  success: boolean;
  service: string;
  action: LinuxUiServiceAction;
  dangerous: boolean;
  output: string;
  status_excerpt: string;
}

export interface LinuxUiServiceActionResponse {
  success: boolean;
  performed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  service_action: LinuxUiServiceActionResult;
}

export type LinuxUiProcessAction = "terminate" | "kill_force";

export interface LinuxUiProcessItem {
  pid: number;
  user: string;
  cpu_percent: number | null;
  memory_percent: number | null;
  elapsed: string;
  command: string;
  args: string;
}

export interface LinuxUiProcessesPayload {
  limit: number;
  summary: {
    total: number;
    high_cpu: number;
    high_memory: number;
  };
  top_cpu: LinuxUiProcessItem[];
  top_memory: LinuxUiProcessItem[];
}

export interface LinuxUiProcessesResponse {
  success: boolean;
  observed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  processes: LinuxUiProcessesPayload;
}

export interface LinuxUiProcessActionPayload {
  pid: number;
  action: LinuxUiProcessAction;
}

export interface LinuxUiProcessActionResult {
  success: boolean;
  pid: number;
  action: LinuxUiProcessAction;
  dangerous: boolean;
  output: string;
  still_running: boolean;
  process_excerpt: string;
}

export interface LinuxUiProcessActionResponse {
  success: boolean;
  performed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  process_action: LinuxUiProcessActionResult;
}

export interface LinuxUiLogPreset {
  key: string;
  label: string;
  description: string;
  available: boolean;
}

export interface LinuxUiLogsPayload {
  source: string;
  service: string;
  lines: number;
  available: boolean;
  content: string;
  presets: LinuxUiLogPreset[];
}

export interface LinuxUiLogsResponse {
  success: boolean;
  observed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  logs: LinuxUiLogsPayload;
}

export interface LinuxUiDiskMount {
  filesystem: string;
  mount: string;
  size_gb: number | null;
  used_gb: number | null;
  available_gb: number | null;
  percent: number | null;
}

export interface LinuxUiDiskPathStat {
  path: string;
  size_mb: number | null;
}

export interface LinuxUiDiskPayload {
  summary: {
    mounts: number;
    critical_mounts: number;
    top_directory_mb: number | null;
    largest_log_mb: number | null;
    cleanup_candidates: number;
  };
  mounts: LinuxUiDiskMount[];
  top_directories: LinuxUiDiskPathStat[];
  large_logs: LinuxUiDiskPathStat[];
  cleanup_candidates: string[];
}

export interface LinuxUiDiskResponse {
  success: boolean;
  observed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  disk: LinuxUiDiskPayload;
}

export interface LinuxUiPackageItem {
  name: string;
  version: string;
}

export interface LinuxUiPackagesPayload {
  package_manager: string;
  installed: LinuxUiPackageItem[];
  updates: string[];
  summary: {
    installed_common: number;
    update_candidates: number;
  };
}

export interface LinuxUiPackagesResponse {
  success: boolean;
  observed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  packages: LinuxUiPackagesPayload;
}

export type LinuxUiDockerAction = "start" | "stop" | "restart";

export interface LinuxUiDockerContainer {
  id: string;
  name: string;
  image: string;
  state: string;
  status: string;
  running_for: string;
  ports: string;
  cpu_percent: string;
  memory_percent: string;
  memory_usage: string;
  network_io: string;
  block_io: string;
}

export interface LinuxUiDockerPayload {
  ready: boolean;
  error: string;
  summary: {
    total: number;
    running: number;
    exited: number;
    restarting: number;
    paused: number;
  };
  containers: LinuxUiDockerContainer[];
}

export interface LinuxUiDockerResponse {
  success: boolean;
  observed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  docker: LinuxUiDockerPayload;
}

export interface LinuxUiDockerLogsPayload {
  container: string;
  lines: number;
  content: string;
}

export interface LinuxUiDockerLogsResponse {
  success: boolean;
  observed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  docker_logs: LinuxUiDockerLogsPayload;
}

export interface LinuxUiDockerActionPayload {
  container: string;
  action: LinuxUiDockerAction;
}

export interface LinuxUiDockerActionResult {
  success: boolean;
  container: string;
  action: LinuxUiDockerAction;
  dangerous: boolean;
  output: string;
  inspect_excerpt: string;
}

export interface LinuxUiDockerActionResponse {
  success: boolean;
  performed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  docker_action: LinuxUiDockerActionResult;
}

export interface LinuxUiNetworkAddress {
  family: string;
  address: string;
  scope: string;
}

export interface LinuxUiNetworkInterface {
  name: string;
  state: string;
  mtu: number | null;
  kind: string;
  mac: string;
  flags: string[];
  addresses: LinuxUiNetworkAddress[];
}

export interface LinuxUiListeningSocket {
  protocol: string;
  state: string;
  local_address: string;
  peer_address: string;
  process: string;
}

export interface LinuxUiNetworkPayload {
  tools: {
    ip: boolean;
    ss: boolean;
  };
  summary: {
    interfaces: number;
    addresses: number;
    routes: number;
    listening: number;
  };
  interfaces: LinuxUiNetworkInterface[];
  routes: string[];
  listening: LinuxUiListeningSocket[];
}

export interface LinuxUiNetworkResponse {
  success: boolean;
  observed_at: string;
  server: Pick<FrontendServer, "id" | "name" | "host" | "username">;
  network: LinuxUiNetworkPayload;
}

export interface SftpTransferProgress {
  loaded: number;
  total?: number;
}

export interface SftpDownloadResult {
  blob: Blob;
  filename: string;
  size: number;
}

export interface FrontendGroup {
  id: number | null;
  name: string;
  server_count: number;
}

export type ServerGroupRole = "owner" | "admin" | "member" | "viewer";
export type ServerGroupSubscriptionKind = "follow" | "favorite";

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
}

export interface AccessGroup {
  id: number;
  name: string;
  member_count: number;
  members?: Array<{ id: number; username: string }>;
}

export interface AccessPermission {
  id: number;
  user_id: number;
  username: string;
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
  chat_model_claude: string;
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
  claude: string[];
  current: {
    default_provider: string;
    chat_gemini: string;
    chat_grok: string;
    chat_openai: string;
    chat_claude: string;
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
  });
}

export async function authLogout() {
  return apiFetch<{ success: boolean }>("/api/auth/logout/", { method: "POST" });
}

export async function fetchFrontendBootstrap() {
  return apiFetch<FrontendBootstrapResponse>("/servers/api/frontend/bootstrap/");
}

function parseContentDispositionFilename(headerValue: string | null): string | null {
  const raw = (headerValue || "").trim();
  if (!raw) return null;

  const utf8Match = raw.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }

  const quotedMatch = raw.match(/filename="([^"]+)"/i);
  if (quotedMatch?.[1]) return quotedMatch[1];

  const bareMatch = raw.match(/filename=([^;]+)/i);
  return bareMatch?.[1]?.trim() || null;
}

async function buildBinaryRequestHeaders(method = "POST"): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};
  if (isMutationRequest(method)) {
    const csrfToken = await ensureCsrfToken();
    if (csrfToken) headers["X-CSRFToken"] = csrfToken;
  }
  return headers;
}

function makeApiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

function extractPathBasename(path: string): string {
  const normalized = String(path || "").replace(/\/+$/, "");
  const parts = normalized.split("/");
  return parts[parts.length - 1] || "download";
}

export function saveBlobAsFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function listServerFiles(serverId: number, path = ".") {
  const query = new URLSearchParams({ path }).toString();
  return apiFetch<SftpListResponse>(`/servers/api/${serverId}/files/?${query}`);
}

export async function fetchLinuxUiCapabilities(serverId: number) {
  return apiFetch<LinuxUiCapabilitiesResponse>(`/servers/api/${serverId}/ui/capabilities/`);
}

export async function fetchLinuxUiOverview(serverId: number) {
  return apiFetch<LinuxUiOverviewResponse>(`/servers/api/${serverId}/ui/overview/`);
}

export async function fetchLinuxUiServices(serverId: number, limit = 120) {
  return apiFetch<LinuxUiServicesResponse>(`/servers/api/${serverId}/ui/services/?limit=${limit}`);
}

export async function fetchLinuxUiServiceLogs(serverId: number, service: string, lines = 80) {
  const params = new URLSearchParams({ service, lines: String(lines) }).toString();
  return apiFetch<LinuxUiServiceLogsResponse>(`/servers/api/${serverId}/ui/services/logs/?${params}`);
}

export async function runLinuxUiServiceAction(serverId: number, payload: LinuxUiServiceActionPayload) {
  return apiFetch<LinuxUiServiceActionResponse>(`/servers/api/${serverId}/ui/services/action/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchLinuxUiProcesses(serverId: number, limit = 80) {
  return apiFetch<LinuxUiProcessesResponse>(`/servers/api/${serverId}/ui/processes/?limit=${limit}`);
}

export async function runLinuxUiProcessAction(serverId: number, payload: LinuxUiProcessActionPayload) {
  return apiFetch<LinuxUiProcessActionResponse>(`/servers/api/${serverId}/ui/processes/action/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchLinuxUiLogs(serverId: number, options?: { source?: string; service?: string; lines?: number }) {
  const params = new URLSearchParams();
  if (options?.source) params.set("source", options.source);
  if (options?.service) params.set("service", options.service);
  if (options?.lines) params.set("lines", String(options.lines));
  const query = params.toString();
  return apiFetch<LinuxUiLogsResponse>(`/servers/api/${serverId}/ui/logs/${query ? `?${query}` : ""}`);
}

export async function fetchLinuxUiDisk(serverId: number) {
  return apiFetch<LinuxUiDiskResponse>(`/servers/api/${serverId}/ui/disk/`);
}

export async function fetchLinuxUiPackages(serverId: number) {
  return apiFetch<LinuxUiPackagesResponse>(`/servers/api/${serverId}/ui/packages/`);
}

export async function fetchLinuxUiDocker(serverId: number) {
  return apiFetch<LinuxUiDockerResponse>(`/servers/api/${serverId}/ui/docker/`);
}

export async function fetchLinuxUiDockerLogs(serverId: number, container: string, lines = 80) {
  const params = new URLSearchParams({ container, lines: String(lines) }).toString();
  return apiFetch<LinuxUiDockerLogsResponse>(`/servers/api/${serverId}/ui/docker/logs/?${params}`);
}

export async function runLinuxUiDockerAction(serverId: number, payload: LinuxUiDockerActionPayload) {
  return apiFetch<LinuxUiDockerActionResponse>(`/servers/api/${serverId}/ui/docker/action/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchLinuxUiNetwork(serverId: number) {
  return apiFetch<LinuxUiNetworkResponse>(`/servers/api/${serverId}/ui/network/`);
}

export async function renameServerFile(serverId: number, path: string, newName: string) {
  return apiFetch<SftpMutationResponse>(`/servers/api/${serverId}/files/rename/`, {
    method: "POST",
    body: JSON.stringify({ path, new_name: newName }),
  });
}

export async function deleteServerFile(serverId: number, path: string, recursive = false) {
  return apiFetch<SftpMutationResponse>(`/servers/api/${serverId}/files/delete/`, {
    method: "POST",
    body: JSON.stringify({ path, recursive }),
  });
}

export async function createServerFolder(serverId: number, path: string, name: string) {
  return apiFetch<SftpMutationResponse>(`/servers/api/${serverId}/files/mkdir/`, {
    method: "POST",
    body: JSON.stringify({ path, name }),
  });
}

export async function readServerTextFile(serverId: number, path: string) {
  const params = new URLSearchParams({ path }).toString();
  return apiFetch<SftpTextFileResponse>(`/servers/api/${serverId}/files/read/?${params}`);
}

export async function writeServerTextFile(serverId: number, path: string, content: string) {
  return apiFetch<SftpTextFileResponse>(`/servers/api/${serverId}/files/write/`, {
    method: "POST",
    body: JSON.stringify({ path, content }),
  });
}

export async function uploadServerFiles(
  serverId: number,
  options: {
    path: string;
    files: File[];
    overwrite?: boolean;
    signal?: AbortSignal;
    onProgress?: (progress: SftpTransferProgress) => void;
  },
) {
  if (isDemoMode()) {
    options.onProgress?.({ loaded: 1, total: 1 });
    return {
      success: true,
      path: options.path,
      entries: options.files.map((file) => ({
        name: file.name,
        path: `${options.path.replace(/\/$/, "")}/${file.name}`,
        kind: "file" as const,
        is_dir: false,
        is_symlink: false,
        size: file.size,
        permissions: "-rw-r--r--",
        modified_at: Math.floor(Date.now() / 1000),
      })),
    } satisfies SftpMutationResponse;
  }

  const headers = await buildBinaryRequestHeaders("POST");
  const form = new FormData();
  form.append("path", options.path || ".");
  if (options.overwrite) form.append("overwrite", "true");
  for (const file of options.files) {
    form.append("files", file);
  }

  return new Promise<SftpMutationResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abortHandler = () => xhr.abort();

    xhr.open("POST", makeApiUrl(`/servers/api/${serverId}/files/upload/`));
    xhr.withCredentials = true;
    Object.entries(headers).forEach(([key, value]) => xhr.setRequestHeader(key, value));

    xhr.upload.onprogress = (event) => {
      options.onProgress?.({
        loaded: event.loaded,
        total: event.lengthComputable ? event.total : undefined,
      });
    };

    xhr.onload = () => {
      try {
        const data = xhr.responseText ? JSON.parse(xhr.responseText) : {};
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data as SftpMutationResponse);
          return;
        }
        reject(new Error(String(data?.error || `HTTP ${xhr.status}`)));
      } catch {
        reject(new Error(`HTTP ${xhr.status}`));
      }
    };

    xhr.onerror = () => reject(new Error("Upload failed"));
    xhr.onabort = () => reject(new DOMException("Upload aborted", "AbortError"));

    if (options.signal) {
      if (options.signal.aborted) {
        xhr.abort();
        return;
      }
      options.signal.addEventListener("abort", abortHandler, { once: true });
    }

    xhr.onloadend = () => {
      if (options.signal) {
        options.signal.removeEventListener("abort", abortHandler);
      }
    };

    xhr.send(form);
  });
}

export async function downloadServerFile(
  serverId: number,
  options: {
    path: string;
    signal?: AbortSignal;
    onProgress?: (progress: SftpTransferProgress) => void;
  },
) {
  if (isDemoMode()) {
    const blob = new Blob([`Demo download for ${options.path}\n`], { type: "text/plain;charset=utf-8" });
    options.onProgress?.({ loaded: blob.size, total: blob.size });
    return {
      blob,
      filename: extractPathBasename(options.path),
      size: blob.size,
    } satisfies SftpDownloadResult;
  }

  const headers = await buildBinaryRequestHeaders("POST");
  const response = await fetch(makeApiUrl(`/servers/api/${serverId}/files/download/`), {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: JSON.stringify({ path: options.path }),
    signal: options.signal,
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  const filename =
    parseContentDispositionFilename(response.headers.get("Content-Disposition")) || extractPathBasename(options.path);
  const totalHeader = Number(response.headers.get("Content-Length") || 0);
  const total = Number.isFinite(totalHeader) && totalHeader > 0 ? totalHeader : undefined;

  if (!response.body) {
    const blob = await response.blob();
    options.onProgress?.({ loaded: blob.size, total: blob.size });
    return { blob, filename, size: blob.size } satisfies SftpDownloadResult;
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let loaded = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) {
      chunks.push(value);
      loaded += value.byteLength;
      options.onProgress?.({ loaded, total });
    }
  }

  const blob = new Blob(chunks as BlobPart[], { type: response.headers.get("Content-Type") || "application/octet-stream" });
  return { blob, filename, size: loaded } satisfies SftpDownloadResult;
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

export async function listServerKnowledge(serverId: number) {
  return apiFetch<{
    success: boolean;
    items: Array<{
      id: number;
      title: string;
      content: string;
      category: string;
      category_label: string;
      source: string;
      source_label: string;
      confidence: number;
      is_active: boolean;
      updated_at: string | null;
    }>;
    categories: Array<{ value: string; label: string }>;
  }>(`/servers/api/${serverId}/knowledge/`);
}

export async function createServerKnowledge(
  serverId: number,
  payload: { title: string; content: string; category?: string; is_active?: boolean },
) {
  return apiFetch<{ success: boolean; id?: number; error?: string }>(`/servers/api/${serverId}/knowledge/create/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateServerKnowledge(
  serverId: number,
  knowledgeId: number,
  payload: { title?: string; content?: string; category?: string; is_active?: boolean },
) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/${serverId}/knowledge/${knowledgeId}/update/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteServerKnowledge(serverId: number, knowledgeId: number) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/${serverId}/knowledge/${knowledgeId}/delete/`, {
    method: "POST",
  });
}

export async function getGlobalServerContext() {
  return apiFetch<{
    rules: string;
    forbidden_commands: string[];
    required_checks: string[];
    environment_vars: Record<string, string>;
  }>("/servers/api/global-context/");
}

export async function saveGlobalServerContext(payload: {
  rules?: string;
  forbidden_commands?: string[] | string;
  required_checks?: string[] | string;
  environment_vars?: Record<string, string>;
}) {
  return apiFetch<{ success: boolean; error?: string }>("/servers/api/global-context/save/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getGroupServerContext(groupId: number) {
  return apiFetch<{
    id: number;
    name: string;
    rules: string;
    forbidden_commands: string[];
    environment_vars: Record<string, string>;
  }>(`/servers/api/groups/${groupId}/context/`);
}

export async function saveGroupServerContext(
  groupId: number,
  payload: { rules?: string; forbidden_commands?: string[] | string; environment_vars?: Record<string, string> },
) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/groups/${groupId}/context/save/`, {
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

export async function refreshModels(provider: "gemini" | "grok" | "openai" | "claude") {
  return apiFetch<{ success: boolean; provider: string; models: string[]; count: number }>("/api/models/refresh/", {
    method: "POST",
    body: JSON.stringify({ provider }),
  });
}

export async function fetchSettingsActivity(limit = 30, days = 14) {
  return apiFetch<ActivityLogsResponse>(`/api/settings/activity/?limit=${limit}&days=${days}`);
}

export async function fetchAccessUsers() {
  return apiFetch<{ users: AccessUser[] }>("/api/access/users/");
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
  return apiFetch<{ groups: AccessGroup[] }>("/api/access/groups/");
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
  return apiFetch<{ permissions: AccessPermission[]; features: Array<{ value: string; label: string }> }>(
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

// ---------------------------------------------------------------------------
// Monitoring API
// ---------------------------------------------------------------------------

export interface ServerHealth {
  server_id: number;
  server_name: string;
  host: string;
  status: "healthy" | "warning" | "critical" | "unreachable" | "unknown";
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  load_1m: number | null;
  uptime_seconds: number | null;
  response_time_ms: number | null;
  checked_at: string | null;
}

export interface ServerAlertItem {
  id: number;
  server_id: number;
  server_name: string;
  alert_type: string;
  severity: "info" | "warning" | "critical";
  title: string;
  message: string;
  is_resolved?: boolean;
  resolved_at?: string | null;
  created_at: string;
  metadata?: Record<string, unknown>;
}

export interface MonitoringDashboard {
  success: boolean;
  servers: ServerHealth[];
  alerts: ServerAlertItem[];
  summary: {
    total_servers: number;
    healthy: number;
    warning: number;
    critical: number;
    unreachable: number;
    unknown: number;
    active_alerts: number;
    avg_cpu: number;
    avg_memory: number;
    avg_disk: number;
  };
  recent_activity: Array<{
    id: number;
    action: string;
    category: string;
    description: string;
    entity_name: string;
    created_at: string;
  }>;
}

export async function fetchMonitoringDashboard() {
  return apiFetch<MonitoringDashboard>("/servers/api/monitoring/dashboard/");
}

export interface HealthCheck {
  id: number;
  status: string;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  load_1m: number | null;
  load_5m: number | null;
  load_15m: number | null;
  memory_used_mb: number | null;
  memory_total_mb: number | null;
  disk_used_gb: number | null;
  disk_total_gb: number | null;
  uptime_seconds: number | null;
  process_count: number | null;
  response_time_ms: number | null;
  is_deep: boolean;
  checked_at: string;
}

export async function fetchServerHealth(serverId: number, hours = 24) {
  return apiFetch<{ success: boolean; server_id: number; server_name: string; checks: HealthCheck[] }>(
    `/servers/api/${serverId}/health/?hours=${hours}`,
  );
}

export async function triggerHealthCheck(serverId: number, deep = false) {
  return apiFetch<{ success: boolean; check: HealthCheck }>(`/servers/api/${serverId}/health/check/`, {
    method: "POST",
    body: JSON.stringify({ deep }),
  });
}

export async function fetchAlerts(params?: { server_id?: number; severity?: string; resolved?: boolean; limit?: number }) {
  const q = new URLSearchParams();
  if (params?.server_id) q.set("server_id", String(params.server_id));
  if (params?.severity) q.set("severity", params.severity);
  if (params?.resolved !== undefined) q.set("resolved", String(params.resolved));
  if (params?.limit) q.set("limit", String(params.limit));
  const qs = q.toString();
  return apiFetch<{ success: boolean; alerts: ServerAlertItem[] }>(`/servers/api/alerts/${qs ? `?${qs}` : ""}`);
}

export async function resolveAlert(alertId: number) {
  return apiFetch<{ success: boolean }>(`/servers/api/alerts/${alertId}/resolve/`, { method: "POST" });
}

// ---------------------------------------------------------------------------
// Admin Dashboard API
// ---------------------------------------------------------------------------

export interface AdminDashboardData {
  online_users: { count: number; total_registered: number; users: Array<{ username: string; action: string; time: string }> };
  ai: { requests_today: number };
  terminals: { active: number; connections: Array<{ server: string; user: string; connected_at: string }> };
  agents: { running: number; today: number; succeeded_24h: number; failed_24h: number; success_rate: number };
  api_usage: Record<string, { calls: number; input_tokens: number; output_tokens: number; errors: number; cost_usd: number }>;
  api_calls_today: number;
  providers: Record<string, { enabled: boolean; model: string }>;
  servers: { total: number; active: number };
  tasks: { total: number; in_progress: number };
  hourly_activity: Array<{ hour: string; count: number }>;
  top_users: Array<{ username: string; total: number; ai_requests: number; terminal_sessions: number }>;
  recent_activity: Array<{ user: string; category: string; action: string; time: string }>;
  fleet_health: { avg_cpu: number; avg_memory: number; avg_disk: number; healthy: number; warning: number; critical: number; unreachable: number };
  active_alerts_count: number;
  alerts: Array<{ server: string; type: string; severity: string; title: string; time: string }>;
  app_version: string;
}

export async function fetchAdminDashboard() {
  return apiFetch<{ success: boolean; data: AdminDashboardData }>("/api/admin/dashboard/");
}

export interface AdminUserActivity {
  id: number;
  user_id: number;
  username: string;
  category: string;
  action: string;
  status: string;
  description: string;
  entity_type: string;
  entity_name: string;
  ip_address: string;
  created_at: string;
}

export async function fetchAdminUsersActivity(params?: { user_id?: number; category?: string; search?: string; limit?: number; offset?: number; days?: number }) {
  const q = new URLSearchParams();
  if (params?.user_id) q.set("user_id", String(params.user_id));
  if (params?.category) q.set("category", params.category);
  if (params?.search) q.set("search", params.search);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  if (params?.days) q.set("days", String(params.days));
  const qs = q.toString();
  return apiFetch<{ success: boolean; total: number; events: AdminUserActivity[] }>(`/api/admin/users/activity/${qs ? `?${qs}` : ""}`);
}

export interface AdminUserSession {
  user_id: number;
  username: string;
  email: string;
  is_staff: boolean;
  last_action: string;
  last_category: string;
  last_activity: string;
  active_terminals: number;
  today_actions: number;
}

export async function fetchAdminUsersSessions() {
  return apiFetch<{ success: boolean; online_count: number; total_registered: number; active_today: number; sessions: AdminUserSession[] }>(
    "/api/admin/users/sessions/",
  );
}

// ---------------------------------------------------------------------------
// Monitoring Config API
// ---------------------------------------------------------------------------

export interface MonitoringConfig {
  success: boolean;
  thresholds: {
    cpu_warn: number;
    cpu_crit: number;
    mem_warn: number;
    mem_crit: number;
    disk_warn: number;
    disk_crit: number;
  };
  stats: {
    total_checks: number;
    active_alerts: number;
    last_check_at: string | null;
    monitored_servers: number;
  };
}

export async function fetchMonitoringConfig() {
  return apiFetch<MonitoringConfig>("/servers/api/monitoring/config/");
}

export async function saveMonitoringConfig(thresholds: Record<string, number>) {
  return apiFetch<{ success: boolean }>("/servers/api/monitoring/config/", {
    method: "POST",
    body: JSON.stringify({ thresholds }),
  });
}

export async function aiAnalyzeServer(serverId: number) {
  return apiFetch<{ success: boolean; analysis: string; server_name: string }>(`/servers/api/${serverId}/ai-analyze/`, {
    method: "POST",
  });
}

// ---------------------------------------------------------------------------
// Agents API (mini + full)
// ---------------------------------------------------------------------------

export interface AgentItem {
  id: number;
  name: string;
  mode: "mini" | "full" | "multi";
  mode_display: string;
  agent_type: string;
  agent_type_display: string;
  server_count: number;
  server_names: string[];
  schedule_minutes: number;
  is_enabled: boolean;
  commands: string[];
  ai_prompt: string;
  goal: string;
  system_prompt: string;
  max_iterations: number;
  allow_multi_server: boolean;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_id: number | null;
  active_run_id: number | null;
}

export interface AgentTemplate {
  type: string;
  name: string;
  mode: "mini" | "full" | "multi";
  commands: string[];
  ai_prompt: string;
  command_count: number;
  goal?: string;
  system_prompt?: string;
  allow_multi_server?: boolean;
  stop_conditions?: string[];
}

export interface AgentRunResult {
  run_id: number;
  server_name: string;
  status: string;
  ai_analysis: string;
  duration_ms: number;
  commands_output: Array<{ cmd: string; stdout: string; stderr: string; exit_code: number; duration_ms: number }>;
  total_iterations?: number;
  final_report?: string;
}

export interface AgentRunDetail {
  id: number;
  agent_id: number;
  agent_name: string;
  agent_type: string;
  agent_mode: string;
  server_name: string;
  status: string;
  ai_analysis: string;
  commands_output: Array<{ cmd: string; stdout: string; stderr: string; exit_code: number; duration_ms: number }>;
  duration_ms: number;
  started_at: string;
  completed_at: string | null;
  iterations_log: Array<{
    iteration: number;
    thought: string;
    action: string | null;
    args: Record<string, unknown>;
    observation: string;
    timestamp: string;
  }>;
  tool_calls: Array<{
    tool: string;
    args: Record<string, unknown>;
    result: string;
    duration_ms: number;
    timestamp: string;
  }>;
  total_iterations: number;
  connected_servers: Array<{ server_id: number; server_name: string }>;
  final_report: string;
  pending_question: string;
  plan_tasks: Array<{
    id: number;
    name: string;
    description: string;
    status: "pending" | "running" | "done" | "failed" | "skipped";
    thought: string;
    iterations: Array<{
      iteration: number;
      thought: string;
      action: string | null;
      args: Record<string, unknown>;
      observation: string;
      timestamp: string;
    }>;
    result: string;
    error: string;
    orchestrator_decision: { action: string; reason?: string; message?: string } | null;
    started_at: string | null;
    completed_at: string | null;
  }>;
  orchestrator_log: Array<{ role: string; content: string; timestamp: string }>;
}

export async function fetchAgents(mode?: string) {
  const url = mode ? `/servers/api/agents/?mode=${mode}` : "/servers/api/agents/";
  return apiFetch<{ success: boolean; agents: AgentItem[] }>(url);
}

export async function fetchAgentTemplates() {
  return apiFetch<{ success: boolean; templates: AgentTemplate[] }>("/servers/api/agents/templates/");
}

export async function createAgent(payload: {
  name?: string;
  mode?: string;
  agent_type: string;
  server_ids: number[];
  commands?: string[];
  ai_prompt?: string;
  schedule_minutes?: number;
  goal?: string;
  system_prompt?: string;
  max_iterations?: number;
  allow_multi_server?: boolean;
  tools_config?: Record<string, boolean>;
  stop_conditions?: string[];
  session_timeout_seconds?: number;
  max_connections?: number;
}) {
  return apiFetch<{ success: boolean; id: number }>("/servers/api/agents/create/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAgent(agentId: number, payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean }>(`/servers/api/agents/${agentId}/update/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteAgent(agentId: number) {
  return apiFetch<{ success: boolean }>(`/servers/api/agents/${agentId}/delete/`, { method: "POST" });
}

export async function runAgent(agentId: number, serverId?: number) {
  return apiFetch<{ success: boolean; runs: AgentRunResult[]; run_id?: number }>(`/servers/api/agents/${agentId}/run/`, {
    method: "POST",
    body: JSON.stringify(serverId ? { server_id: serverId } : {}),
  });
}

export async function stopAgent(agentId: number, runId?: number) {
  return apiFetch<{ success: boolean }>(`/servers/api/agents/${agentId}/stop/`, {
    method: "POST",
    body: JSON.stringify(runId ? { run_id: runId } : {}),
  });
}

export async function fetchAgentRuns(agentId: number, limit = 20) {
  return apiFetch<{ success: boolean; runs: AgentRunDetail[] }>(`/servers/api/agents/${agentId}/runs/?limit=${limit}`);
}

export async function fetchAgentRunDetail(runId: number) {
  return apiFetch<{ success: boolean; run: AgentRunDetail }>(`/servers/api/agents/runs/${runId}/`);
}

export async function fetchAgentRunLog(runId: number) {
  return apiFetch<{
    success: boolean;
    iterations_log: AgentRunDetail["iterations_log"];
    tool_calls: AgentRunDetail["tool_calls"];
    total_iterations: number;
    status: string;
    pending_question: string;
    plan_tasks: AgentRunDetail["plan_tasks"];
  }>(`/servers/api/agents/runs/${runId}/log/`);
}

export async function replyToAgent(runId: number, answer: string) {
  return apiFetch<{ success: boolean }>(`/servers/api/agents/runs/${runId}/reply/`, {
    method: "POST",
    body: JSON.stringify({ answer }),
  });
}

export async function updatePipelineTask(
  runId: number,
  taskId: number,
  payload: { action: "update" | "delete"; name?: string; description?: string },
) {
  return apiFetch<{ success: boolean; plan_tasks: AgentRunDetail["plan_tasks"] }>(
    `/servers/api/agents/runs/${runId}/tasks/${taskId}/update/`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function aiRefinePipelineTask(
  runId: number,
  taskId: number,
  instruction: string,
) {
  return apiFetch<{
    success: boolean;
    task: AgentRunDetail["plan_tasks"][number];
    plan_tasks: AgentRunDetail["plan_tasks"];
    error?: string;
    raw?: string;
  }>(`/servers/api/agents/runs/${runId}/tasks/${taskId}/ai-refine/`, {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });
}

export async function approvePipelinePlan(runId: number) {
  return apiFetch<{
    success: boolean;
    run_id: number;
    status: string;
    runs: Array<{
      run_id: number;
      server_name: string;
      status: string;
      ai_analysis: string;
      duration_ms: number;
      total_iterations: number;
      final_report: string;
    }>;
    error?: string;
  }>(`/servers/api/agents/runs/${runId}/approve-plan/`, { method: "POST" });
}

export interface DashboardRunItem {
  id: number;
  agent_id: number;
  agent_name: string;
  agent_mode: "mini" | "full" | "multi";
  agent_type: string;
  server_name: string;
  server_id: number;
  status: string;
  total_iterations: number;
  duration_ms: number;
  started_at: string;
  completed_at: string | null;
  pending_question: string;
  connected_servers: Array<{ server_id: number; server_name: string }>;
  ai_analysis: string;
  final_report: string;
  commands_output: Array<{ cmd: string; stdout: string; stderr: string; exit_code: number; duration_ms: number }>;
}

export async function fetchAgentDashboardRuns() {
  return apiFetch<{ success: boolean; active: DashboardRunItem[]; recent: DashboardRunItem[] }>("/servers/api/agents/dashboard/");
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

export interface PipelineListItem {
  id: number;
  name: string;
  description: string;
  icon: string;
  tags: string[];
  is_shared: boolean;
  is_template: boolean;
  node_count: number;
  created_at: string;
  updated_at: string;
  last_run: PipelineLastRun | null;
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
}

export interface AgentConfig {
  id: number;
  name: string;
  description: string;
  icon: string;
  system_prompt: string;
  instructions: string;
  model: string;
  max_iterations: number;
  allowed_tools: string[];
  skill_slugs: string[];
  skills: StudioSkill[];
  skill_errors?: string[];
  mcp_servers: Array<{ id: number; name: string; transport: string }>;
  server_scope: Array<{ id: number; name: string }>;
}

export interface StudioSkill {
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

export interface MCPServer {
  id: number;
  name: string;
  description: string;
  transport: "stdio" | "sse";
  command: string;
  args: string[];
  env: Record<string, string>;
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

export interface PipelineTrigger {
  id: number;
  pipeline_id: number;
  node_id: string;
  name: string;
  trigger_type: "manual" | "webhook" | "schedule";
  is_active: boolean;
  webhook_token: string;
  webhook_url: string;
  cron_expression: string;
  webhook_payload_map: Record<string, unknown>;
  last_triggered_at: string | null;
}

export interface StudioPipelineAssistantPayload {
  pipeline_id?: number | null;
  pipeline_name: string;
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  selected_node?: PipelineNode | null;
  user_message: string;
}

export interface StudioPipelineGraphPatchNode {
  ref: string;
  type: string;
  data: Record<string, unknown>;
  label?: string;
  x_offset?: number;
  y_offset?: number;
}

export interface StudioPipelineGraphPatchEdge {
  source: string;
  target: string;
  label?: string;
  source_handle?: string;
  target_handle?: string;
}

export interface StudioPipelineGraphPatch {
  anchor_node_id: string | null;
  nodes: StudioPipelineGraphPatchNode[];
  edges: StudioPipelineGraphPatchEdge[];
}

export interface StudioPipelineAssistantResponse {
  reply: string;
  target_node_id: string | null;
  node_patch: Record<string, unknown>;
  graph_patch: StudioPipelineGraphPatch;
  warnings: string[];
}

// Pipelines
export const studioPipelines = {
  list: (q?: string) => apiFetch<PipelineListItem[]>(`/api/studio/pipelines/${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  get: (id: number) => apiFetch<PipelineDetail>(`/api/studio/pipelines/${id}/`),
  create: (data: Partial<PipelineDetail>) => apiFetch<PipelineDetail>("/api/studio/pipelines/", { method: "POST", body: JSON.stringify(data) }),
  update: (id: number, data: Partial<PipelineDetail>) => apiFetch<PipelineDetail>(`/api/studio/pipelines/${id}/`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (id: number) => apiFetch<{ ok: boolean }>(`/api/studio/pipelines/${id}/`, { method: "DELETE" }),
  run: (id: number, context?: Record<string, unknown>) => apiFetch<PipelineRun>(`/api/studio/pipelines/${id}/run/`, { method: "POST", body: JSON.stringify({ context: context || {} }) }),
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
