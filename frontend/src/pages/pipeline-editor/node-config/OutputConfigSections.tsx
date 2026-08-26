import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { AdvancedDisclosure, FieldHint, NodeFormSection } from "../PanelPrimitives";
import { localize } from "../presentation";
import { ManagedSecretInput } from "./ManagedSecretInput";
import type { Lang, NodeData, SetNodeData, SetNodePatch } from "./types";

export function OutputConfigSections({
  type,
  data,
  lang,
  onSet,
  onSetMany,
}: {
  type: string;
  data: NodeData;
  lang: Lang;
  onSet: SetNodeData;
  onSetMany: SetNodePatch;
}) {
  if (type === "output/webhook") return <WebhookOutput data={data} lang={lang} onSet={onSet} />;
  if (type === "output/report") return <ReportOutput data={data} lang={lang} onSet={onSet} />;
  if (type === "output/email") return <EmailOutput data={data} lang={lang} onSet={onSet} onSetMany={onSetMany} />;
  if (type === "output/telegram") return <TelegramOutput data={data} lang={lang} onSet={onSet} onSetMany={onSetMany} />;
  return null;
}

function WebhookOutput({ data, lang, onSet }: OutputProps) {
  return (
    <NodeFormSection title={localize(lang, "Доставка", "Delivery")}>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "URL вебхука", "Webhook URL")}</Label>
        <Input
          value={(data.url as string) || ""}
          onChange={(event) => onSet("url", event.target.value)}
          placeholder="https://hooks.example.com/..."
          className="h-8 text-xs"
        />
      </div>
    </NodeFormSection>
  );
}

function ReportOutput({ data, lang, onSet }: OutputProps) {
  return (
    <NodeFormSection title={localize(lang, "Доставка", "Delivery")}>
      <div className="space-y-1.5">
        <Label className="text-xs">{localize(lang, "Шаблон отчёта", "Report template")}</Label>
        <Textarea
          value={(data.template as string) || ""}
          onChange={(event) => onSet("template", event.target.value)}
          placeholder={"# Report\n\n{node_id_output}"}
          className="text-xs font-mono resize-none"
          rows={4}
        />
        <FieldHint>{localize(lang, "Оставьте пустым для авто-сгенерированного отчёта.", "Leave empty for auto-generated report.")}</FieldHint>
      </div>
    </NodeFormSection>
  );
}

function EmailOutput({ data, lang, onSet, onSetMany }: SecretOutputProps) {
  return (
    <>
      <NodeFormSection title={localize(lang, "Доставка", "Delivery")}>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Получатели", "To email(s)")}</Label>
          <Input value={(data.to_email as string) || ""} onChange={(event) => onSet("to_email", event.target.value)} placeholder="admin@example.com, team@example.com" className="h-8 text-xs" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Тема письма", "Subject")}</Label>
          <Input value={(data.subject as string) || ""} onChange={(event) => onSet("subject", event.target.value)} placeholder={localize(lang, "Отчёт сценария: {pipeline_name}", "Pipeline Report: {pipeline_name}")} className="h-8 text-xs" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Шаблон тела письма", "Body template")}</Label>
          <Textarea value={(data.body as string) || ""} onChange={(event) => onSet("body", event.target.value)} placeholder={"# Report\n\n{all_outputs}"} className="text-xs font-mono resize-none" rows={3} />
          <FieldHint>{localize(lang, "Оставьте пустым для авто-сгенерированного текста.", "Leave empty for auto-generated body.")}</FieldHint>
        </div>
      </NodeFormSection>
      <AdvancedDisclosure title={localize(lang, "Дополнительно", "Advanced")}>
        <SmtpSettings data={data} lang={lang} onSet={onSet} onSetMany={onSetMany} />
      </AdvancedDisclosure>
    </>
  );
}

function TelegramOutput({ data, lang, onSet, onSetMany }: SecretOutputProps) {
  return (
    <>
      <NodeFormSection title={localize(lang, "Доставка", "Delivery")}>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Шаблон сообщения", "Message template")}</Label>
          <Textarea
            value={(data.message as string) || ""}
            onChange={(event) => onSet("message", event.target.value)}
            placeholder={"*{pipeline_name}*\n\n{all_outputs}"}
            className="text-xs resize-none"
            rows={4}
          />
          <FieldHint>
            {localize(lang, "Поддерживает Markdown. Переменные:", "Supports Markdown. Variables:")} <code>{"{all_outputs}"}</code>,{" "}
            <code>{"{node_id_output}"}</code>
          </FieldHint>
        </div>
      </NodeFormSection>
      <AdvancedDisclosure title={localize(lang, "Дополнительно", "Advanced")}>
        <ManagedSecretInput
          data={data}
          label={localize(lang, "Токен бота", "Bot Token")}
          lang={lang}
          onSetMany={onSetMany}
          placeholder="1234567890:AAF..."
          secretKey="bot_token"
        />
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "ID чата", "Chat ID")}</Label>
          <Input value={(data.chat_id as string) || ""} onChange={(event) => onSet("chat_id", event.target.value)} placeholder="-100123456789" className="h-8 text-xs font-mono" />
          <FieldHint>{localize(lang, "ID чата можно найти через @userinfobot или @getidsbot.", "Use @userinfobot or @getidsbot to find your chat ID.")}</FieldHint>
        </div>
      </AdvancedDisclosure>
    </>
  );
}

function SmtpSettings({ data, lang, onSet, onSetMany }: SecretOutputProps) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground uppercase">{localize(lang, "Настройки SMTP", "SMTP settings")}</Label>
      <Input value={(data.smtp_host as string) || ""} onChange={(event) => onSet("smtp_host", event.target.value)} placeholder="smtp.gmail.com" className="h-8 text-xs" />
      <div className="flex gap-2">
        <Input value={(data.smtp_user as string) || ""} onChange={(event) => onSet("smtp_user", event.target.value)} placeholder="user@gmail.com" className="h-8 text-xs flex-1" />
        <div className="w-44 shrink-0">
          <ManagedSecretInput
            data={data}
            label={localize(lang, "Пароль SMTP", "SMTP password")}
            lang={lang}
            onSetMany={onSetMany}
            placeholder={localize(lang, "пароль приложения", "app password")}
            secretKey="smtp_password"
          />
        </div>
      </div>
    </div>
  );
}

type OutputProps = {
  data: NodeData;
  lang: Lang;
  onSet: SetNodeData;
};

type SecretOutputProps = OutputProps & {
  onSetMany: SetNodePatch;
};
