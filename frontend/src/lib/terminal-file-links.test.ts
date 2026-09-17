import { describe, expect, it } from "vitest";
import {
  extractTextFilenames,
  hasTextExtension,
  isLikelyEditablePathToken,
  joinRemotePath,
  parsePromptCwd,
} from "./terminal-file-links";

describe("terminal-file-links", () => {
  it("detects plain ls columns", () => {
    expect(extractTextFilenames("app.py  config.yml  README.md")).toEqual(
      expect.arrayContaining(["app.py", "config.yml", "README.md"]),
    );
  });

  it("detects relative paths with directories", () => {
    expect(extractTextFilenames("src/main.py  ./cfg.yml  ../deploy/app.sh")).toEqual(
      expect.arrayContaining(["src/main.py", "./cfg.yml", "../deploy/app.sh"]),
    );
  });

  it("detects absolute and home-relative paths", () => {
    expect(extractTextFilenames("edit /etc/nginx/nginx.conf and ~/proj/app.py")).toEqual(
      expect.arrayContaining(["/etc/nginx/nginx.conf", "~/proj/app.py"]),
    );
  });

  it("detects ls -l trailing filename", () => {
    const line = "-rw-r--r-- 1 root root 4096 May 19 10:00 settings.py";
    expect(extractTextFilenames(line)).toEqual(["settings.py"]);
  });

  it("detects ls -l symlink target when it is a text path", () => {
    const line = "lrwxrwxrwx 1 root root 12 May 19 10:00 nginx.conf -> /etc/nginx/nginx.conf";
    expect(extractTextFilenames(line)).toEqual(["/etc/nginx/nginx.conf"]);
  });

  it("detects ls -l symlink name when target is not a text path", () => {
    const line = "lrwxrwxrwx 1 root root 12 May 19 10:00 app.py -> /opt/bin/app";
    expect(extractTextFilenames(line)).toEqual(["app.py"]);
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
    expect(joinRemotePath("/home/user", "src/main.py")).toBe("/home/user/src/main.py");
    expect(joinRemotePath("/home/user", "./cfg.yml")).toBe("/home/user/cfg.yml");
  });

  it("expands tilde using home path", () => {
    expect(joinRemotePath("~", "app.py", "/home/ubuntu")).toBe("/home/ubuntu/app.py");
    expect(joinRemotePath("~/projects", "app.py", "/home/ubuntu")).toBe("/home/ubuntu/projects/app.py");
    expect(joinRemotePath("/tmp", "~/x.py", "/home/ubuntu")).toBe("/home/ubuntu/x.py");
  });

  it("recognizes extension whitelist", () => {
    expect(hasTextExtension("script.sh")).toBe(true);
    expect(hasTextExtension("archive.tar.gz")).toBe(false);
    expect(hasTextExtension("src/main.py")).toBe(true);
  });

  it("filters noise tokens that are not editable paths", () => {
    expect(isLikelyEditablePathToken("12.log")).toBe(false);
    expect(isLikelyEditablePathToken("app.py;rm")).toBe(false);
    expect(isLikelyEditablePathToken("src/main.py")).toBe(true);
    expect(extractTextFilenames("see src/main.py and also app.py")).toContain("src/main.py");
  });
});
