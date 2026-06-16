export function toJsonEditorText(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "{}";
  const entries = Object.keys(value as Record<string, unknown>);
  if (!entries.length) return "{}";
  return JSON.stringify(value, null, 2);
}

export function parseJsonObjectText(text: string): { value: Record<string, unknown> | null; error: string | null } {
  const trimmed = text.trim();
  if (!trimmed) return { value: {}, error: null };
  try {
    const parsed = JSON.parse(trimmed);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { value: null, error: "JSON must be an object" };
    }
    return { value: parsed as Record<string, unknown>, error: null };
  } catch (error) {
    return { value: null, error: error instanceof Error ? error.message : "Invalid JSON" };
  }
}

export function buildSchemaTemplate(inputSchema?: Record<string, unknown>) {
  const properties = (inputSchema?.properties as Record<string, Record<string, unknown>> | undefined) || {};
  const next: Record<string, unknown> = {};
  Object.entries(properties).forEach(([key, property]) => {
    const type = property?.type;
    if (type === "boolean") next[key] = false;
    else if (type === "number" || type === "integer") next[key] = 0;
    else if (type === "array") next[key] = [];
    else if (type === "object") next[key] = {};
    else next[key] = `{${key}}`;
  });
  return next;
}

export function getSchemaProperties(inputSchema?: Record<string, unknown>) {
  const properties = inputSchema?.properties;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) return {};
  return properties as Record<string, Record<string, unknown>>;
}

export function getSchemaRequiredFields(inputSchema?: Record<string, unknown>) {
  const required = inputSchema?.required;
  return new Set(Array.isArray(required) ? required.map((item) => String(item)) : []);
}

export function getSchemaType(property: Record<string, unknown>) {
  const rawType = property.type;
  if (Array.isArray(rawType)) return String(rawType.find((item) => item !== "null") || "string");
  return String(rawType || "string");
}

export function coerceSchemaFormValue(rawValue: string | boolean, property: Record<string, unknown>) {
  const type = getSchemaType(property);
  if (type === "boolean") return Boolean(rawValue);
  if (type === "integer") {
    const parsed = Number.parseInt(String(rawValue), 10);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  if (type === "number") {
    const parsed = Number.parseFloat(String(rawValue));
    return Number.isFinite(parsed) ? parsed : 0;
  }
  if (type === "array" || type === "object") {
    try {
      const parsed = JSON.parse(String(rawValue || (type === "array" ? "[]" : "{}")));
      if (type === "array" && Array.isArray(parsed)) return parsed;
      if (type === "object" && parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
    } catch {
      // Keep the previous valid value from the JSON editor when a nested field is invalid.
    }
    return type === "array" ? [] : {};
  }
  return String(rawValue);
}

export function getSchemaFormTextValue(value: unknown, property: Record<string, unknown>) {
  const type = getSchemaType(property);
  if (type === "array" || type === "object") return JSON.stringify(value ?? (type === "array" ? [] : {}), null, 2);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value === undefined || value === null) return "";
  return String(value);
}
