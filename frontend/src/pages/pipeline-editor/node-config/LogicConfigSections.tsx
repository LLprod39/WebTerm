import type { ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import { AdvancedDisclosure, FieldHint, NodeFormSection } from "../PanelPrimitives";
import { localize } from "../presentation";
import type { Lang, NodeData, SetNodeData } from "./types";

export function LogicConfigSections({
  type,
  data,
  lang,
  onSet,
}: {
  type: string;
  data: NodeData;
  lang: Lang;
  onSet: SetNodeData;
}) {
  if (type === "logic/condition") return <ConditionConfig data={data} lang={lang} onSet={onSet} />;
  if (type === "logic/merge") return <MergeConfig data={data} lang={lang} onSet={onSet} />;
  if (type === "logic/wait") return <WaitConfig data={data} lang={lang} onSet={onSet} />;
  if (type === "logic/human_approval") return <HumanApprovalConfig data={data} lang={lang} onSet={onSet} />;
  if (type === "logic/telegram_input") return <TelegramInputConfig data={data} lang={lang} onSet={onSet} />;
  return null;
}

function ConditionConfig({ data, lang, onSet }: LogicProps) {
  const checkType = (data.check_type as string) || "contains";

  return (
    <NodeFormSection
      title={localize(lang, "Вход / условие", "Input / condition")}
      description={localize(lang, "Выберите правило, по которому пайплайн пойдёт в ветку Да или Нет.", "Choose the rule that routes the pipeline into True or False.")}
    >
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Тип проверки", "Check type")}</Label>
        <Select value={checkType} onValueChange={(value) => onSet("check_type", value)}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="contains">{localize(lang, "Вывод содержит текст", "Output contains")}</SelectItem>
            <SelectItem value="not_contains">{localize(lang, "Вывод не содержит текст", "Output does not contain")}</SelectItem>
            <SelectItem value="status_ok">{localize(lang, "Предыдущая нода успешна", "Previous node succeeded")}</SelectItem>
            <SelectItem value="status_failed">{localize(lang, "Предыдущая нода упала", "Previous node failed")}</SelectItem>
            <SelectItem value="always_true">{localize(lang, "Всегда Да", "Always true")}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {checkType.includes("contains") && (
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Текст для проверки", "Check value")}</Label>
          <Input value={(data.check_value as string) || ""} onChange={(event) => onSet("check_value", event.target.value)} placeholder="error" className="h-8 text-xs" />
          {!String(data.check_value || "").trim() ? (
            <p className="text-[10px] text-red-400">
              {localize(lang, "Обязательное поле для contains/not_contains.", "Required for contains/not_contains checks.")}
            </p>
          ) : null}
        </div>
      )}
    </NodeFormSection>
  );
}

function MergeConfig({ data, lang, onSet }: LogicProps) {
  return (
    <NodeFormSection
      title={localize(lang, "Исполнение", "Execution")}
      description={localize(lang, "Как несколько входящих веток снова сходятся в одну.", "How several incoming branches join back into one flow.")}
    >
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Режим слияния", "Merge mode")}</Label>
        <Select value={(data.mode as string) || "all"} onValueChange={(value) => onSet("mode", value)}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{localize(lang, "all: ждать все активные ветки", "all: wait for every activated branch")}</SelectItem>
            <SelectItem value="any">{localize(lang, "any: продолжить после первой готовой ветки", "any: continue after the first completed branch")}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <FieldHint>
        {localize(lang, "Используйте Merge вместо нескольких входящих связей прямо в action/output ноду.", "Use merge nodes instead of wiring multiple incoming edges directly into an action or output node.")}
      </FieldHint>
    </NodeFormSection>
  );
}

function WaitConfig({ data, lang, onSet }: LogicProps) {
  return (
    <NodeFormSection title={localize(lang, "Исполнение", "Execution")}>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Длительность паузы (минуты)", "Wait duration (minutes)")}</Label>
        <Input
          type="number"
          value={(data.wait_minutes as number) ?? 20}
          onChange={(event) => onSet("wait_minutes", parseFloat(event.target.value) || 1)}
          className="h-8 text-xs"
          min={0.1}
          max={1440}
          step={0.5}
        />
        <FieldHint>{localize(lang, "Диапазон: 0.1-1440 минут, максимум 24 часа.", "Range: 0.1-1440 minutes, 24h max.")}</FieldHint>
      </div>
    </NodeFormSection>
  );
}

function HumanApprovalConfig({ data, lang, onSet }: LogicProps) {
  return (
    <>
      <NodeFormSection
        title={localize(lang, "Доставка", "Delivery")}
        description={localize(lang, "Куда отправить approve/reject запрос оператору.", "Where to send the operator approve/reject request.")}
      >
        <div className="space-y-1.5">
          <Label className="text-xs">Кому (email)</Label>
          <Input value={(data.to_email as string) || ""} onChange={(event) => onSet("to_email", event.target.value)} placeholder="или из Studio → Notifications" className="h-8 text-xs" />
        </div>
        <div className="flex items-start justify-between gap-3 rounded-lg border border-yellow-500/20 bg-yellow-500/10 px-3 py-2">
          <div className="min-w-0 space-y-1">
            <Label className="text-xs">{localize(lang, "Ручная ссылка без доставки", "Manual link only")}</Label>
            <p className="text-[11px] leading-relaxed text-yellow-100/80">
              {localize(
                lang,
                "Email/Telegram не отправляются; запуск будет ждать решение по approve/reject ссылкам.",
                "Email/Telegram are not sent; the run waits for a decision through approve/reject links.",
              )}
            </p>
          </div>
          <Switch
            aria-label={localize(lang, "Ручная ссылка без доставки", "Manual link only")}
            data-testid="manual-link-only-switch"
            checked={Boolean(data.manual_link_only)}
            onCheckedChange={(checked) => onSet("manual_link_only", checked)}
            className="mt-0.5"
          />
        </div>
        <TextTemplateField label="Тема письма (шаблон)" value={(data.email_subject as string) || ""} placeholder="Пусто = тема по умолчанию" hint={<>Переменные: {"{pipeline_name}"}, {"{run_id}"}</>} onChange={(value) => onSet("email_subject", value)} />
        <TextTemplateField label="Текст письма (шаблон)" value={(data.email_body as string) || ""} placeholder="Пусто = текст по умолчанию. Переменные ниже." hint={<>{ "{approve_url}"}, {"{reject_url}"}, {"{all_outputs}"}, {"{timeout_minutes}"}</>} rows={8} textarea onChange={(value) => onSet("email_body", value)} />
        <TimeoutField data={data} lang={lang} onSet={onSet} min={5} />
      </NodeFormSection>
      <AdvancedDisclosure title={localize(lang, "Дополнительно", "Advanced")}>
        <TelegramSettings data={data} onSet={onSet} tokenKey="tg_bot_token" chatKey="tg_chat_id" tokenPlaceholder="Bot Token (from @BotFather)" chatPlaceholder="Chat ID (e.g. -100123456)" />
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Base URL для ссылок подтверждения", "Base URL for approval links")}</Label>
          <Input value={(data.base_url as string) || ""} onChange={(event) => onSet("base_url", event.target.value)} placeholder="https://your-server.example.com" className="h-8 text-xs" />
          <FieldHint>{localize(lang, "Используется в approve/reject ссылках из уведомлений.", "Used in approve/reject URLs sent in notifications.")}</FieldHint>
        </div>
        <TextTemplateField label="Сообщение в Telegram (шаблон)" value={(data.message as string) || ""} placeholder="{approve_url}, {reject_url}..." textarea rows={4} onChange={(value) => onSet("message", value)} />
        <SmtpSettings data={data} lang={lang} onSet={onSet} />
      </AdvancedDisclosure>
    </>
  );
}

function TelegramInputConfig({ data, lang, onSet }: LogicProps) {
  return (
    <>
      <NodeFormSection
        title={localize(lang, "Доставка", "Delivery")}
        description={localize(lang, "Сообщение оператору и ожидание текстового ответа.", "Prompt the operator and wait for a plain text reply.")}
      >
        <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/10 px-3 py-2 text-[11px] text-cyan-100">
          Этот узел отправляет сообщение в Telegram и ждёт обычный текстовый reply от оператора.
        </div>
        <TextTemplateField label={localize(lang, "Шаблон сообщения", "Message template")} value={(data.message as string) || ""} placeholder="Опишите, какой ответ вы ждёте от оператора" hint={<>Переменные: {"{pipeline_name}"}, {"{run_id}"}, {"{all_outputs}"}</>} rows={6} textarea onChange={(value) => onSet("message", value)} />
        <TimeoutField data={data} lang={lang} onSet={onSet} min={1} />
      </NodeFormSection>
      <AdvancedDisclosure title={localize(lang, "Дополнительно", "Advanced")}>
        <TelegramSettings data={data} onSet={onSet} tokenKey="tg_bot_token" chatKey="tg_chat_id" />
      </AdvancedDisclosure>
    </>
  );
}

function TimeoutField({ data, lang, onSet, min }: LogicProps & { min: number }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{localize(lang, "Timeout, минут", "Timeout (minutes)")}</Label>
      <Input type="number" value={(data.timeout_minutes as number) ?? 120} onChange={(event) => onSet("timeout_minutes", parseFloat(event.target.value) || 120)} className="h-8 text-xs" min={min} max={10080} />
    </div>
  );
}

function TextTemplateField({ label, value, placeholder, hint, rows = 4, textarea = false, onChange }: { label: string; value: string; placeholder?: string; hint?: ReactNode; rows?: number; textarea?: boolean; onChange: (value: string) => void }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      {textarea ? (
        <Textarea value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} className="text-xs resize-none" rows={rows} />
      ) : (
        <Input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} className="h-8 text-xs" />
      )}
      {hint ? <FieldHint>{hint}</FieldHint> : null}
    </div>
  );
}

function TelegramSettings({
  data,
  tokenKey,
  chatKey,
  tokenPlaceholder = "или глобально в Studio → Notifications",
  chatPlaceholder = "-100123456789",
  onSet,
}: {
  data: NodeData;
  tokenKey: string;
  chatKey: string;
  tokenPlaceholder?: string;
  chatPlaceholder?: string;
  onSet: SetNodeData;
}) {
  return (
    <>
      <div className="space-y-1.5">
        <Label className="text-xs">Bot Token</Label>
        <Input value={(data[tokenKey] as string) || ""} onChange={(event) => onSet(tokenKey, event.target.value)} placeholder={tokenPlaceholder} className="h-8 text-xs font-mono" />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">Chat ID</Label>
        <Input value={(data[chatKey] as string) || ""} onChange={(event) => onSet(chatKey, event.target.value)} placeholder={chatPlaceholder} className="h-8 text-xs font-mono" />
      </div>
    </>
  );
}

function SmtpSettings({ data, lang, onSet }: LogicProps) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground uppercase">{localize(lang, "SMTP для писем подтверждения", "SMTP for approval email")}</Label>
      <Input value={(data.smtp_host as string) || ""} onChange={(event) => onSet("smtp_host", event.target.value)} placeholder="smtp.gmail.com" className="h-8 text-xs" />
      <div className="flex gap-2">
        <Input value={(data.smtp_user as string) || ""} onChange={(event) => onSet("smtp_user", event.target.value)} placeholder="user@gmail.com" className="h-8 text-xs flex-1" />
        <Input value={(data.smtp_password as string) || ""} onChange={(event) => onSet("smtp_password", event.target.value)} placeholder="app password" type="password" className="h-8 text-xs w-28" />
      </div>
    </div>
  );
}

type LogicProps = {
  data: NodeData;
  lang: Lang;
  onSet: SetNodeData;
};
