import type { PipelineNode, StudioCapabilityNode } from "@/lib/api";

export type PipelineClientValidationError = {
  nodeId: string;
  field: string;
  messageRu: string;
  messageEn: string;
};

function schemaProperties(manifest?: StudioCapabilityNode): Record<string, Record<string, unknown>> {
  const inputSchema = manifest?.input_schema;
  const properties = inputSchema?.properties;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) return {};
  return properties as Record<string, Record<string, unknown>>;
}

function hasValue(value: unknown): boolean {
  if (value === undefined || value === null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  return true;
}

function isPlaceholder(value: unknown): boolean {
  return typeof value === "string" && /^\{[A-Za-z_][A-Za-z0-9_]*\}$/.test(value.trim());
}

function normaliseEnumCandidate(value: unknown, property: Record<string, unknown>): string {
  const type = property.type;
  if (type === "string") return String(value).trim();
  return String(value);
}

function schemaTypeMatches(value: unknown, expectedType: string): boolean {
  if (isPlaceholder(value)) return true;
  if (expectedType === "string") return typeof value === "string";
  if (expectedType === "integer") {
    if (typeof value === "boolean") return false;
    const parsed = Number(value);
    return Number.isInteger(parsed);
  }
  if (expectedType === "number") {
    if (typeof value === "boolean") return false;
    return Number.isFinite(Number(value));
  }
  if (expectedType === "boolean") {
    return typeof value === "boolean" || ["true", "false", "1", "0", "yes", "no"].includes(String(value).trim().toLowerCase());
  }
  if (expectedType === "array") return Array.isArray(value);
  if (expectedType === "object") return Boolean(value && typeof value === "object" && !Array.isArray(value));
  return true;
}

function mcpArgumentsFromNode(node: PipelineNode, errors: PipelineClientValidationError[]): Record<string, unknown> | null {
  const data = node.data || {};
  if (typeof data.arguments_text === "string" && data.arguments_text.trim()) {
    try {
      const parsed = JSON.parse(data.arguments_text);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      // The backend reports the exact JSON parser error; keep the local error short.
    }
    errors.push({
      nodeId: node.id,
      field: "arguments_text",
      messageRu: `Node '${node.id}': arguments_text должен быть JSON-объектом.`,
      messageEn: `Node '${node.id}': arguments_text must be a JSON object.`,
    });
    return null;
  }
  const args = data.arguments;
  if (args === undefined || args === null || args === "") return {};
  if (args && typeof args === "object" && !Array.isArray(args)) return args as Record<string, unknown>;
  errors.push({
    nodeId: node.id,
    field: "arguments",
    messageRu: `Node '${node.id}': arguments должен быть JSON-объектом.`,
    messageEn: `Node '${node.id}': arguments must be a JSON object.`,
  });
  return null;
}

function validateMcpArgumentsAgainstEmbeddedSchema(node: PipelineNode, errors: PipelineClientValidationError[]): void {
  if (node.type !== "agent/mcp_call") return;
  const data = node.data || {};
  const inputSchema = data.input_schema;
  if (!inputSchema || typeof inputSchema !== "object" || Array.isArray(inputSchema)) return;
  const properties = (inputSchema as { properties?: unknown }).properties;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) return;
  const args = mcpArgumentsFromNode(node, errors);
  if (!args) return;

  const required = (inputSchema as { required?: unknown }).required;
  if (Array.isArray(required)) {
    required.map(String).forEach((field) => {
      if (!hasValue(args[field])) {
        errors.push({
          nodeId: node.id,
          field,
          messageRu: `Node '${node.id}': MCP argument '${field}' обязателен по input_schema.`,
          messageEn: `Node '${node.id}': MCP argument '${field}' is required by input_schema.`,
        });
      }
    });
  }

  Object.entries(properties as Record<string, Record<string, unknown>>).forEach(([field, property]) => {
    const value = args[field];
    if (!hasValue(value)) return;
    const enumValues = Array.isArray(property.enum) ? property.enum.map(String) : [];
    if (enumValues.length && !isPlaceholder(value) && !enumValues.includes(String(value))) {
      errors.push({
        nodeId: node.id,
        field,
        messageRu: `Node '${node.id}': MCP argument '${field}' должен быть одним из: ${enumValues.join(", ")}.`,
        messageEn: `Node '${node.id}': MCP argument '${field}' must be one of: ${enumValues.join(", ")}.`,
      });
      return;
    }
    const rawType = property.type;
    const types = Array.isArray(rawType) ? rawType.map(String) : typeof rawType === "string" ? [rawType] : [];
    if (types.length && !types.some((type) => schemaTypeMatches(value, type))) {
      errors.push({
        nodeId: node.id,
        field,
        messageRu: `Node '${node.id}': MCP argument '${field}' не совпадает с типом schema: ${types.join(" или ")}.`,
        messageEn: `Node '${node.id}': MCP argument '${field}' must match schema type: ${types.join(" or ")}.`,
      });
    }
  });
}

function validateNodeAgainstManifest(
  node: PipelineNode,
  manifest: StudioCapabilityNode | undefined,
  errors: PipelineClientValidationError[],
): void {
  const data = node.data || {};
  const properties = schemaProperties(manifest);
  Object.entries(properties).forEach(([field, property]) => {
    const value = data[field];
    if (!hasValue(value)) return;

    const enumValues = Array.isArray(property.enum) ? property.enum.map(String) : [];
    if (enumValues.length && !enumValues.includes(normaliseEnumCandidate(value, property))) {
      errors.push({
        nodeId: node.id,
        field,
        messageRu: `Node '${node.id}': поле '${field}' должно быть одним из: ${enumValues.join(", ")}.`,
        messageEn: `Node '${node.id}': field '${field}' must be one of: ${enumValues.join(", ")}.`,
      });
      return;
    }

    if (property.type === "integer" || property.type === "number") {
      const parsed = property.type === "integer"
        ? Number.parseInt(String(value), 10)
        : Number.parseFloat(String(value));
      if (!Number.isFinite(parsed)) {
        errors.push({
          nodeId: node.id,
          field,
          messageRu: `Node '${node.id}': поле '${field}' должно быть числом.`,
          messageEn: `Node '${node.id}': field '${field}' must be numeric.`,
        });
        return;
      }
      const minimum = typeof property.minimum === "number" ? property.minimum : null;
      const maximum = typeof property.maximum === "number" ? property.maximum : null;
      if (minimum !== null && parsed < minimum) {
        errors.push({
          nodeId: node.id,
          field,
          messageRu: `Node '${node.id}': поле '${field}' должно быть не меньше ${minimum}.`,
          messageEn: `Node '${node.id}': field '${field}' must be at least ${minimum}.`,
        });
        return;
      }
      if (maximum !== null && parsed > maximum) {
        errors.push({
          nodeId: node.id,
          field,
          messageRu: `Node '${node.id}': поле '${field}' должно быть не больше ${maximum}.`,
          messageEn: `Node '${node.id}': field '${field}' must be at most ${maximum}.`,
        });
      }
    }
  });
}

export function getPipelineClientValidationErrors(
  nodes: PipelineNode[],
  manifests: StudioCapabilityNode[] = [],
): PipelineClientValidationError[] {
  const errors: PipelineClientValidationError[] = [];
  const manifestByType = new Map(manifests.map((manifest) => [manifest.type, manifest]));

  for (const node of nodes) {
    validateNodeAgainstManifest(node, manifestByType.get(node.type), errors);
    validateMcpArgumentsAgainstEmbeddedSchema(node, errors);

    if (node.type === "logic/condition") {
      const data = node.data || {};
      const checkType = String(data.check_type || "contains").trim();
      if ((checkType === "contains" || checkType === "not_contains") && !String(data.check_value || "").trim()) {
        errors.push({
          nodeId: node.id,
          field: "check_value",
          messageRu: `Condition '${node.id}': заполните текст для проверки.`,
          messageEn: `Condition '${node.id}': fill in the check value.`,
        });
      }
    }
  }

  return errors;
}
