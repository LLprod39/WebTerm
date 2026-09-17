const INTERNAL_REDIRECT_ORIGIN = "https://webterm.invalid";
const ENCODED_SEPARATOR_OR_CONTROL = /%(?:2f|5c|0[0-9a-f]|1[0-9a-f]|7f)/i;

function containsControlCharacter(value: string): boolean {
  return Array.from(value).some((character) => {
    const codePoint = character.codePointAt(0) ?? 0;
    return codePoint <= 0x1f || codePoint === 0x7f;
  });
}

export function normalizeInternalRedirectPath(value: unknown): string | null {
  if (typeof value !== "string" || !value) return null;
  if (value !== value.trim()) return null;
  if (!value.startsWith("/") || value.startsWith("//")) return null;
  if (value.includes("\\") || containsControlCharacter(value) || ENCODED_SEPARATOR_OR_CONTROL.test(value)) {
    return null;
  }

  try {
    const base = new URL(INTERNAL_REDIRECT_ORIGIN);
    const parsed = new URL(value, base);
    if (parsed.origin !== base.origin || !parsed.pathname.startsWith("/") || parsed.pathname.startsWith("//")) {
      return null;
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return null;
  }
}
