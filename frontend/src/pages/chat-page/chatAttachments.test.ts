import { describe, expect, it } from "vitest";

import {
  CHAT_ATTACH_CONTENTS_MARKER,
  formatAttachedFilesForDisplay,
  formatAttachedFilesForModel,
  isLikelyTextChatAttachment,
  stripAttachedFileContents,
  type AttachedChatFile,
} from "./chatAttachments";
import { visibleOperatorUserText } from "./operatorUserText";

function file(partial: Partial<AttachedChatFile> & Pick<AttachedChatFile, "name">): AttachedChatFile {
  return {
    id: partial.id || partial.name,
    size: partial.size ?? 12,
    content: partial.content ?? "",
    truncated: partial.truncated ?? false,
    kind: partial.kind ?? "text",
    name: partial.name,
  };
}

describe("chatAttachments", () => {
  it("treats common config/source extensions as text", () => {
    expect(isLikelyTextChatAttachment({ name: "deploy.yml", type: "" })).toBe(true);
    expect(isLikelyTextChatAttachment({ name: "notes.md", type: "" })).toBe(true);
    expect(isLikelyTextChatAttachment({ name: "image.png", type: "image/png" })).toBe(false);
  });

  it("builds a visible summary and model payload", () => {
    const files = [
      file({ name: "a.yml", content: "hosts: all", kind: "text" }),
      file({ name: "bin.bin", kind: "binary", size: 40 }),
    ];
    expect(formatAttachedFilesForDisplay(files, "ru")).toContain("Файлы: a.yml, bin.bin");
    const model = formatAttachedFilesForModel(files);
    expect(model).toContain(CHAT_ATTACH_CONTENTS_MARKER);
    expect(model).toContain("hosts: all");
    expect(model).toContain("binary or unreadable");
  });

  it("keeps the files summary in the bubble while hiding bodies and pins", () => {
    const raw = [
      "Проверь playbook",
      "",
      "Файлы: a.yml",
      "",
      CHAT_ATTACH_CONTENTS_MARKER,
      "--- a.yml ---",
      "hosts: all",
      "",
      "Контекст серверов: @prod (ids: 1).",
    ].join("\n");
    expect(stripAttachedFileContents(raw)).not.toContain("hosts: all");
    expect(visibleOperatorUserText(raw)).toBe("Проверь playbook\n\nФайлы: a.yml");
  });
});
