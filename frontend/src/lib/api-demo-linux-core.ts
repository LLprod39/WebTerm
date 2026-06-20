export function demoLinuxUiCoreFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
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
  return undefined;
}
