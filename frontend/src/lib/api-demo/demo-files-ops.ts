/** Early file op demo fallbacks (read/write/chmod/chown). Must run before broader path matches. */
export function demoFilesOpsFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
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
  return undefined;
}
