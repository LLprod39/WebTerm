import { describe, expect, it } from "vitest";
import {
  extractTextFilenames,
  hasTextExtension,
  joinRemotePath,
  parsePromptCwd,
} from "./terminal-file-links";

describe("terminal-file-links", () => {
  it("detects plain ls columns", () => {
    expect(extractTextFilenames("app.py  config.yml  README.md")).toEqual(
      expect.arrayContaining(["app.py", "config.yml", "README.md"]),
    );
  });

  it("detects ls -l trailing filename", () => {
    const line =
      "-rw-r--r-- 1 root root 4096 May 19 10:00 settings.py";
    expect(extractTextFilenames(line)).toEqual(["settings.py"]);
  });

  it("detects ls -l symlink name before arrow", () => {
    const line =
      "lrwxrwxrwx 1 root root 12 May 19 10:00 nginx.conf -> /etc/nginx/nginx.conf";
    expect(extractTextFilenames(line)).toEqual(["nginx.conf"]);
  });

  it("ignores lines without text extensions", () => {
    expect(extractTextFilenames("bin  lib  tmp")).toEqual([]);
  });

  it("parses shell prompt cwd", () => {
    expect(parsePromptCwd("user@host:~/projects/app$ ")).toBe("~/projects/app");
    expect(parsePromptCwd("user@host:/var/www$")).toBe("/var/www");
  });

  it("joins relative paths with cwd", () => {
    expect(joinRemotePath("/home/user", "main.py")).toBe("/home/user/main.py");
    expect(joinRemotePath("/home/user/", "main.py")).toBe("/home/user/main.py");
    expect(joinRemotePath("/etc", "/etc/hosts")).toBe("/etc/hosts");
  });

  it("recognizes extension whitelist", () => {
    expect(hasTextExtension("script.sh")).toBe(true);
    expect(hasTextExtension("archive.tar.gz")).toBe(false);
  });
});
