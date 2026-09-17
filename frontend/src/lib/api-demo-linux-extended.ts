export function demoLinuxUiExtendedFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
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
  return undefined;
}
