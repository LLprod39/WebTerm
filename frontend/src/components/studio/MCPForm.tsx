import { useState } from "react";
import { Loader2, Save } from "lucide-react";

import { ShareAccessEditor } from "@/components/studio/ShareAccessEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { localize, useI18n } from "@/lib/i18n";
import type { MCPServer } from "@/lib/api";

export function MCPForm({
  initial,
  onSave,
  onCancel,
  isPending,
  shareUsers,
  isAdmin,
  canEdit,
}: {
  initial: Partial<MCPServer>;
  onSave: (data: Partial<MCPServer>) => void;
  onCancel: () => void;
  isPending: boolean;
  shareUsers: Array<{ id: number; username: string; email?: string }>;
  isAdmin: boolean;
  canEdit: boolean;
}) {
  const { lang } = useI18n();
  const [form, setForm] = useState<Partial<MCPServer>>({
    name: "",
    description: "",
    transport: "stdio",
    command: "",
    args: [],
    env: {},
    url: "",
    is_shared: false,
    shared_user_ids: [],
    ...initial,
  });
  const readOnly = !canEdit;
  const [argsText, setArgsText] = useState((initial.args || []).join("\n"));
  const [envText, setEnvText] = useState(
    Object.entries(initial.env || {})
      .map(([key, value]) => `${key}=${value}`)
      .join("\n"),
  );
  const [sharedUserIds, setSharedUserIds] = useState<number[]>(initial.shared_user_ids || []);
  const transport = form.transport || "stdio";
  const connectionPreview =
    transport === "stdio"
      ? [form.command, ...argsText.split("\n").map((line) => line.trim()).filter(Boolean)]
          .filter(Boolean)
          .join(" ") || localize(lang, "Команда пока не указана", "Command is not set yet")
      : form.url || localize(lang, "SSE URL пока не указан", "SSE URL is not set yet");

  const setField = (key: keyof MCPServer, value: unknown) => setForm((current) => ({ ...current, [key]: value }));

  const submit = () => {
    const args = argsText.split("\n").map((line) => line.trim()).filter(Boolean);
    const env: Record<string, string> = {};
    for (const line of envText.split("\n")) {
      const [key, ...rest] = line.split("=");
      if (key?.trim()) env[key.trim()] = rest.join("=").trim();
    }
    onSave({ ...form, args, env, shared_user_ids: sharedUserIds });
  };

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-border/70 bg-background/40 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              {localize(lang, "Подключение", "Connection")}
            </div>
            <div className="mt-1 text-sm font-medium text-foreground">
              {transport === "stdio"
                ? localize(lang, "Локальная stdio-команда", "Local stdio command")
                : localize(lang, "Удалённый SSE endpoint", "Remote SSE endpoint")}
            </div>
          </div>
          <div className="rounded-md border border-border/70 bg-card px-2.5 py-1 font-mono text-xs text-muted-foreground">
            {transport}
          </div>
        </div>
        <div className="mt-3 overflow-hidden rounded-lg border border-border/70 bg-card px-3 py-2 font-mono text-xs text-muted-foreground">
          <div className="truncate">{connectionPreview}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_10rem]">
        <div className="flex-1 space-y-1.5">
          <Label className="text-xs">{localize(lang, "Название", "Name")}</Label>
          <Input
            value={form.name || ""}
            onChange={(event) => setField("name", event.target.value)}
            placeholder={localize(lang, "Например, GitHub MCP", "For example, GitHub MCP")}
            disabled={readOnly}
          />
        </div>
        <div className="w-36 space-y-1.5">
          <Label className="text-xs">{localize(lang, "Транспорт", "Transport")}</Label>
          <Select value={transport} onValueChange={(value) => setField("transport", value)} disabled={readOnly}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="stdio">stdio</SelectItem>
              <SelectItem value="sse">SSE</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Описание", "Description")}</Label>
        <Input
          value={form.description || ""}
          onChange={(event) => setField("description", event.target.value)}
          placeholder={localize(lang, "Какие инструменты появятся у агента", "What tools this server exposes")}
          disabled={readOnly}
        />
      </div>

      {transport === "stdio" ? (
        <>
          <div className="space-y-1.5">
            <Label className="text-xs">{localize(lang, "Команда", "Command")}</Label>
            <Input
              value={form.command || ""}
              onChange={(event) => setField("command", event.target.value)}
              placeholder="npx"
              disabled={readOnly}
            />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(lang, "Аргументы", "Arguments")}</Label>
              <Textarea
                value={argsText}
                onChange={(event) => setArgsText(event.target.value)}
                rows={5}
                placeholder={localize(lang, "По одному аргументу на строку", "One argument per line")}
                disabled={readOnly}
                className="font-mono text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{localize(lang, "Переменные окружения", "Environment variables")}</Label>
              <Textarea
                value={envText}
                onChange={(event) => setEnvText(event.target.value)}
                rows={5}
                placeholder="KEY=value"
                disabled={readOnly}
                className="font-mono text-xs"
              />
            </div>
          </div>
        </>
      ) : (
        <div className="space-y-1.5">
          <Label className="text-xs">SSE URL</Label>
          <Input
            value={form.url || ""}
            onChange={(event) => setField("url", event.target.value)}
            placeholder="https://..."
            disabled={readOnly}
          />
        </div>
      )}

      {isAdmin ? (
        <ShareAccessEditor
          title={localize(lang, "Видимость", "Visibility")}
          description={localize(lang, "Администратор может открыть этот MCP всем или только выбранным пользователям.", "Admins can expose this MCP server to everyone or only selected users.")}
          isShared={Boolean(form.is_shared)}
          sharedUserIds={sharedUserIds}
          users={shareUsers}
          disabled={readOnly}
          onSharedChange={(value) => setField("is_shared", value)}
          onToggleUser={(userId) =>
            setSharedUserIds((current) =>
              current.includes(userId) ? current.filter((id) => id !== userId) : [...current, userId],
            )
          }
        />
      ) : null}

      <div className="rounded-xl border border-border/70 bg-background/30 px-4 py-3 text-xs leading-5 text-muted-foreground">
        {localize(lang, "Шаблон заполняет стартовые поля. Перед сохранением проверьте команду, аргументы, URL и переменные окружения.", "Templates fill the starter fields. Review the command, arguments, URL, and environment variables before saving.")}
      </div>

      <div className="sticky bottom-0 -mx-6 -mb-4 flex flex-col-reverse gap-2 border-t border-border/70 bg-card/95 px-6 py-4 backdrop-blur sm:flex-row sm:justify-end">
        <Button variant="outline" size="sm" onClick={onCancel}>
          {localize(lang, "Отмена", "Cancel")}
        </Button>
        <Button size="sm" onClick={submit} disabled={!form.name || readOnly || isPending} className="gap-1.5 sm:min-w-28">
          {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          {localize(lang, "Сохранить", "Save")}
        </Button>
      </div>
    </div>
  );
}
