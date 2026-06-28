import { useCallback, useMemo } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import {
  coerceSchemaFormValue,
  getSchemaFormTextValue,
  getSchemaProperties,
  getSchemaRequiredFields,
  getSchemaType,
} from "../jsonSchemaUtils";
import { NodeFormSection } from "../PanelPrimitives";
import { localize } from "../presentation";

export function PluginSchemaConfigSection({
  data,
  inputSchema,
  lang,
  onSet,
}: {
  data: Record<string, unknown>;
  inputSchema?: Record<string, unknown>;
  lang: "en" | "ru";
  onSet: (key: string, value: unknown) => void;
}) {
  const properties = useMemo(() => getSchemaProperties(inputSchema), [inputSchema]);
  const requiredFields = useMemo(() => getSchemaRequiredFields(inputSchema), [inputSchema]);
  const renderField = useCallback(
    ([field, property]: [string, Record<string, unknown>]) => {
      const value = data[field];
      const enumValues = Array.isArray(property.enum) ? property.enum.map(String) : [];
      const label = `${field}${requiredFields.has(field) ? " *" : ""}`;
      const description = typeof property.description === "string" ? property.description : "";
      const schemaType = getSchemaType(property);

      if (enumValues.length) {
        return (
          <div key={field} className="space-y-1.5">
            <Label className="text-xs">{label}</Label>
            <Select value={String(value ?? "")} onValueChange={(next) => onSet(field, next)}>
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder={localize(lang, "Выберите значение", "Select value")} />
              </SelectTrigger>
              <SelectContent>
                {enumValues.map((item) => (
                  <SelectItem key={item} value={item}>{item}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
          </div>
        );
      }

      if (schemaType === "boolean") {
        return (
          <label key={field} className="flex items-start gap-2 rounded-lg border border-border/70 bg-background/50 px-2.5 py-2">
            <Checkbox checked={Boolean(value)} onCheckedChange={(next) => onSet(field, Boolean(next))} />
            <span className="min-w-0 text-xs">
              <span className="block font-medium text-foreground">{label}</span>
              {description ? <span className="mt-0.5 block text-muted-foreground">{description}</span> : null}
            </span>
          </label>
        );
      }

      if (schemaType === "object" || schemaType === "array") {
        return (
          <div key={field} className="space-y-1.5">
            <Label className="text-xs">{label}</Label>
            <Textarea
              value={getSchemaFormTextValue(value, property)}
              onChange={(event) => onSet(field, coerceSchemaFormValue(event.target.value, property))}
              className="min-h-24 font-mono text-xs"
            />
            {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
          </div>
        );
      }

      return (
        <div key={field} className="space-y-1.5">
          <Label className="text-xs">{label}</Label>
          <Input
            value={getSchemaFormTextValue(value, property)}
            onChange={(event) => onSet(field, coerceSchemaFormValue(event.target.value, property))}
            className="h-8 text-xs"
          />
          {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
        </div>
      );
    },
    [data, lang, onSet, requiredFields],
  );

  if (!Object.keys(properties).length) {
    return null;
  }

  return (
    <NodeFormSection
      title={localize(lang, "Параметры плагина", "Plugin parameters")}
      description={localize(lang, "Поля объявлены в manifest input_schema этого плагина.", "Fields are declared by this plugin manifest input_schema.")}
    >
      <div className="space-y-3">
        {Object.entries(properties).map(renderField)}
      </div>
    </NodeFormSection>
  );
}
