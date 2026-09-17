export function extractSocketPort(localAddress: string) {
  const raw = String(localAddress || "").trim();
  if (!raw) return "";
  const bracketMatch = raw.match(/\]:(\d+)$/);
  if (bracketMatch?.[1]) return bracketMatch[1];
  const plainMatch = raw.match(/:(\d+)$/);
  return plainMatch?.[1] || "";
}

export function isSocketExposed(localAddress: string) {
  const raw = String(localAddress || "").trim().toLowerCase();
  return (
    raw.startsWith("0.0.0.0:") ||
    raw.startsWith("[::]:") ||
    raw.startsWith("*:") ||
    raw.startsWith(":::") ||
    raw === "::"
  );
}
