export function formatCommandListText(value: unknown) {
  if (!Array.isArray(value)) return "";
  return value.map((item) => String(item || "").trim()).filter(Boolean).join("\n");
}

export function parseCommandListText(text: string) {
  return String(text || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}
