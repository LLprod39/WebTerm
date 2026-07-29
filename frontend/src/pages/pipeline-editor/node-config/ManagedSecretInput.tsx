import { KeyRound, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { FieldHint } from "../PanelPrimitives";
import { localize } from "../presentation";
import type { Lang, NodeData, SetNodePatch } from "./types";

export function ManagedSecretInput({
  data,
  label,
  lang,
  onSetMany,
  placeholder,
  secretKey,
}: {
  data: NodeData;
  label: string;
  lang: Lang;
  onSetMany: SetNodePatch;
  placeholder: string;
  secretKey: string;
}) {
  const markerKey = `${secretKey}_configured`;
  const clearKey = `${secretKey}_clear`;
  const inputId = `managed-secret-${secretKey}`;
  const configured = Boolean(data[markerKey]);
  const value = typeof data[secretKey] === "string" ? String(data[secretKey]) : "";

  const setValue = (nextValue: string) => {
    onSetMany({
      [secretKey]: nextValue,
      ...(nextValue.trim() ? { [clearKey]: false } : {}),
    });
  };

  const removeSavedSecret = () => {
    onSetMany({
      [secretKey]: "",
      [clearKey]: true,
      [markerKey]: false,
    });
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={inputId} className="text-xs">{label}</Label>
        {configured ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400">
            <KeyRound className="h-3 w-3" aria-hidden />
            {localize(lang, "Сохранён безопасно", "Stored securely")}
          </span>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <Input
          id={inputId}
          type="password"
          autoComplete="new-password"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={configured ? "••••••••" : placeholder}
          className="h-8 min-w-0 flex-1 text-xs font-mono"
        />
        {configured ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 shrink-0 px-2"
            onClick={removeSavedSecret}
            aria-label={localize(lang, `Удалить сохранённый ${label}`, `Remove saved ${label}`)}
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden />
          </Button>
        ) : null}
      </div>
      <FieldHint>
        {configured
          ? localize(
              lang,
              "Значение не читается из backend. Введите новое только для ротации.",
              "The backend never returns this value. Enter a new one only to rotate it.",
            )
          : localize(
              lang,
              "После сохранения значение шифруется и становится недоступным для чтения.",
              "After saving, this value is encrypted and becomes write-only.",
            )}
      </FieldHint>
    </div>
  );
}
