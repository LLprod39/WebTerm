import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { AdvancedDisclosure, FieldHint, NodeFormSection } from "../PanelPrimitives";
import { localize } from "../presentation";
import type { Lang, NodeData, SetNodeData } from "./types";

export function OutputConfigSections({
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
  if (type === "output/webhook") return <WebhookOutput data={data} lang={lang} onSet={onSet} />;
  if (type === "output/report") return <ReportOutput data={data} lang={lang} onSet={onSet} />;
  if (type === "output/email") return <EmailOutput data={data} lang={lang} onSet={onSet} />;
  if (type === "output/telegram") return <TelegramOutput data={data} lang={lang} onSet={onSet} />;
  return null;
}

function WebhookOutput({ data, lang, onSet }: OutputProps) {
  return (
    <NodeFormSection title={localize(lang, "Доставка", "Delivery")}>
      <div className="space-y-1.5">
        <Label className="text-xs">Webhook URL</Label>
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

function EmailOutput({ data, lang, onSet }: OutputProps) {
  return (
    <>
      <NodeFormSection title={localize(lang, "Доставка", "Delivery")}>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Получатели email", "To email(s)")}</Label>
          <Input value={(data.to_email as string) || ""} onChange={(event) => onSet("to_email", event.target.value)} placeholder="admin@example.com, team@example.com" className="h-8 text-xs" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Тема письма", "Subject")}</Label>
          <Input value={(data.subject as string) || ""} onChange={(event) => onSet("subject", event.target.value)} placeholder="Pipeline Report: {pipeline_name}" className="h-8 text-xs" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{localize(lang, "Шаблон тела письма", "Body template")}</Label>
          <Textarea value={(data.body as string) || ""} onChange={(event) => onSet("body", event.target.value)} placeholder={"# Report\n\n{all_outputs}"} className="text-xs font-mono resize-none" rows={3} />
          <FieldHint>{localize(lang, "Оставьте пустым для авто-сгенерированного текста.", "Leave empty for auto-generated body.")}</FieldHint>
        </div>
      </NodeFormSection>
      <AdvancedDisclosure title={localize(lang, "Дополнительно", "Advanced")}>
        <SmtpSettings data={data} lang={lang} onSet={onSet} />
      </AdvancedDisclosure>
    </>
  );
}

function TelegramOutput({ data, lang, onSet }: OutputProps) {
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
        <div className="space-y-1.5">
          <Label className="text-xs">Bot Token</Label>
          <Input value={(data.bot_token as string) || ""} onChange={(event) => onSet("bot_token", event.target.value)} placeholder="1234567890:AAF..." className="h-8 text-xs font-mono" />
          <FieldHint>{localize(lang, "Получите токен у @BotFather в Telegram.", "Get from @BotFather on Telegram.")}</FieldHint>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Chat ID</Label>
          <Input value={(data.chat_id as string) || ""} onChange={(event) => onSet("chat_id", event.target.value)} placeholder="-100123456789" className="h-8 text-xs font-mono" />
          <FieldHint>{localize(lang, "Chat ID можно найти через @userinfobot или @getidsbot.", "Use @userinfobot or @getidsbot to find your chat ID.")}</FieldHint>
        </div>
      </AdvancedDisclosure>
    </>
  );
}

function SmtpSettings({ data, lang, onSet }: OutputProps) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground uppercase">{localize(lang, "SMTP настройки", "SMTP settings")}</Label>
      <Input value={(data.smtp_host as string) || ""} onChange={(event) => onSet("smtp_host", event.target.value)} placeholder="smtp.gmail.com" className="h-8 text-xs" />
      <div className="flex gap-2">
        <Input value={(data.smtp_user as string) || ""} onChange={(event) => onSet("smtp_user", event.target.value)} placeholder="user@gmail.com" className="h-8 text-xs flex-1" />
        <Input value={(data.smtp_password as string) || ""} onChange={(event) => onSet("smtp_password", event.target.value)} placeholder="app password" type="password" className="h-8 text-xs w-28" />
      </div>
    </div>
  );
}

type OutputProps = {
  data: NodeData;
  lang: Lang;
  onSet: SetNodeData;
};
