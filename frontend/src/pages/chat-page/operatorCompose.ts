/** Parse slash commands and @mentions for Operator chat. */

import { SLASH_COMMANDS } from "./composeCommands";

export type ParsedCompose = {
  /** Message sent to the backend (slash expanded into natural language). */
  message: string;
  /** Mentions resolved as server name chips. */
  mentions: string[];
  /** Original slash if any. */
  slash?: string;
};

const SLASH_TEMPLATES: Record<string, (args: string) => string> = Object.fromEntries(
  SLASH_COMMANDS.filter((c) => c.build).map((c) => [c.trigger, c.build!]),
);

export function parseOperatorCompose(raw: string): ParsedCompose {
  const text = String(raw || "").trim();
  const mentions: string[] = [];
  const mentionRe = /@([A-Za-z0-9._-]{1,80})/g;
  let match: RegExpExecArray | null;
  while ((match = mentionRe.exec(text)) !== null) {
    if (!mentions.includes(match[1])) mentions.push(match[1]);
  }

  if (text.startsWith("/")) {
    const body = text.slice(1);
    const space = body.indexOf(" ");
    const cmd = (space >= 0 ? body.slice(0, space) : body).toLowerCase();
    const args = space >= 0 ? body.slice(space + 1) : "";
    // Browse commands should not be sent as bare text
    if (["servers", "users", "agents"].includes(cmd)) {
      return { message: text, mentions, slash: cmd };
    }
    const template = SLASH_TEMPLATES[cmd];
    if (template) {
      let message = template(args);
      if (mentions.length) {
        message += ` Контекст серверов: ${mentions.map((m) => `@${m}`).join(", ")}.`;
      }
      return { message, mentions, slash: cmd };
    }
  }

  return { message: text, mentions };
}

export function extractPinnedServersFromMentions(
  mentions: string[],
  inventory: Array<{ id: number; name: string }>,
): Array<{ id: number; name: string }> {
  const out: Array<{ id: number; name: string }> = [];
  for (const m of mentions) {
    const lower = m.toLowerCase();
    const hit = inventory.find(
      (s) => s.name.toLowerCase() === lower || String(s.id) === m,
    );
    if (hit && !out.some((x) => x.id === hit.id)) out.push(hit);
  }
  return out;
}
