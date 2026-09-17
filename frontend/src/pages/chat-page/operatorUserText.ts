import { stripAttachedFileContents } from "./chatAttachments";

/** Remove backend-only pin/terminal/file-body context before user text reaches the UI. */
export function visibleOperatorUserText(raw: string) {
  return stripAttachedFileContents(String(raw || ""))
    .replace(/\n\n\[Human terminal on[^\]]*\][\s\S]*$/i, "")
    .replace(/\n\nКонтекст серверов:[\s\S]*$/i, "")
    .replace(/\n\nКонтекст playbook:[\s\S]*$/i, "")
    .replace(/\nКонтекст пользователей:[\s\S]*$/i, "")
    .trim();
}
