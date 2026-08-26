import { useEffect, useMemo, useState, type ElementType } from "react";
import { StudioNav } from "@/components/StudioNav";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Bell,
  Bot,
  CheckCircle2,
  ExternalLink,
  Eye,
  EyeOff,
  Loader2,
  Mail,
  RotateCcw,
  Save,
  Send,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageShell, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import { studioNotifications, type NotificationConfig } from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";

const notificationConfigKeys: Array<keyof NotificationConfig> = [
  "telegram_bot_token",
  "telegram_chat_id",
  "notify_email",
  "smtp_host",
  "smtp_port",
  "smtp_user",
  "smtp_password",
  "from_email",
  "site_url",
];

function normalizeNotificationConfig(config?: Partial<NotificationConfig>) {
  return notificationConfigKeys.reduce<Record<string, string>>((acc, key) => {
    acc[key] = String(config?.[key] ?? "");
    return acc;
  }, {});
}

function PasswordField({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [visible, setVisible] = useState(false);
  const { lang } = useI18n();
  const visibilityLabel = visible
    ? localize(lang, "Скрыть секретное значение", "Hide secret value")
    : localize(lang, "Показать секретное значение", "Show secret value");

  return (
    <div className="relative">
      <Input
        type={visible ? "text" : "password"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="pr-10"
      />
      <button
        type="button"
        className="absolute right-1.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => setVisible((current) => !current)}
        aria-label={visibilityLabel}
        title={visibilityLabel}
      >
        {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

function HelpLink({ href, children }: { href: string; children: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 font-medium text-primary underline decoration-primary/70 underline-offset-2 hover:decoration-primary"
    >
      {children}
      <ExternalLink className="h-3 w-3" />
    </a>
  );
}

function DeliveryStatusRow({
  icon: Icon,
  title,
  description,
  ready,
}: {
  icon: ElementType;
  title: string;
  description: string;
  ready: boolean;
}) {
  const { lang } = useI18n();
  return (
    <div className="workspace-subtle flex items-start justify-between gap-3 rounded-2xl px-4 py-4">
      <div className="flex min-w-0 items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border/70 bg-background/40">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0 space-y-1">
          <div className="text-sm font-medium text-foreground">{title}</div>
          <div className="text-xs leading-5 text-muted-foreground">{description}</div>
        </div>
      </div>
      <StatusBadge
        label={ready ? localize(lang, "Готово", "Ready") : localize(lang, "Не готово", "Not ready")}
        tone={ready ? "success" : "warning"}
        className="shrink-0"
      />
    </div>
  );
}

function TestButton({
  label,
  onTest,
  disabled,
}: {
  label: string;
  onTest: () => Promise<{ ok: boolean; message: string }>;
  disabled?: boolean;
}) {
  const { lang } = useI18n();
  const [result, setResult] = useState<{ ok: boolean; message: string; testedAt: Date } | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    setResult(null);
    try {
      const response = await onTest();
      setResult({ ...response, testedAt: new Date() });
    } catch (error: unknown) {
      setResult({
        ok: false,
        message: error instanceof Error ? error.message : String(error),
        testedAt: new Date(),
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button
        type="button"
        variant="outline"
        onClick={run}
        disabled={disabled || loading}
        className="gap-2"
      >
        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        {label}
      </Button>
      {result ? (
        <div
          className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${
            result.ok
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
              : "border-red-500/30 bg-red-500/10 text-red-200"
          }`}
        >
          {result.ok ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
          <span className="min-w-0">
            <span className="block">{result.message}</span>
            <span className="mt-0.5 block text-muted-foreground">
              {localize(lang, "Проверено", "Tested")} {result.testedAt.toLocaleTimeString(lang === "ru" ? "ru-RU" : "en-US", { hour: "2-digit", minute: "2-digit" })}
            </span>
          </span>
        </div>
      ) : null}
    </div>
  );
}

export default function NotificationsSettingsPage({ showStudioNav = true }: { showStudioNav?: boolean }) {
  const { toast } = useToast();
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Partial<NotificationConfig>>({});

  const { data: config, isLoading } = useQuery({
    queryKey: ["studio", "notifications"],
    queryFn: studioNotifications.get,
  });

  useEffect(() => {
    if (!config) return;
    setForm(config);
  }, [config]);

  const setField = (key: keyof NotificationConfig, value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const normalizedConfig = useMemo(() => JSON.stringify(normalizeNotificationConfig(config)), [config]);
  const normalizedForm = useMemo(() => JSON.stringify(normalizeNotificationConfig(form)), [form]);
  const isDirty = normalizedConfig !== normalizedForm;
  const discardChanges = () => {
    if (!config) return;
    setForm(config);
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = normalizeNotificationConfig(form) as Partial<NotificationConfig>;
      await studioNotifications.save(payload);
      return payload;
    },
    onSuccess: async (payload) => {
      setForm(payload);
      await queryClient.invalidateQueries({ queryKey: ["studio", "notifications"] });
      toast({ description: localize(lang, "Настройки оповещений сохранены.", "Notification settings saved.") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const telegramReady = Boolean(form.telegram_bot_token?.trim() && form.telegram_chat_id?.trim());
  const emailReady = Boolean(form.notify_email?.trim() && form.smtp_host?.trim() && form.smtp_user?.trim());
  const siteReady = Boolean(form.site_url?.trim());

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        {localize(lang, "Загружаю настройки оповещений...", "Loading notification settings...")}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {showStudioNav ? <StudioNav /> : null}
      <div className="flex-1 overflow-auto">
        <PageShell width="6xl">
          <SectionCard
            title={localize(lang, "Оповещения", "Notifications")}
            description={localize(lang, "Telegram, почта и ссылки согласования.", "Telegram, email, and approval links.")}
            icon={<Bell className="h-5 w-5 text-primary" />}
            actions={
              <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending || !isDirty} className="gap-2">
                {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : isDirty ? <Save className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
                {isDirty ? localize(lang, "Сохранить настройки", "Save settings") : localize(lang, "Сохранено", "Saved")}
              </Button>
            }
          >
            <div className="space-y-5">
              <div className="grid gap-3 md:grid-cols-3">
                <DeliveryStatusRow
                  icon={Bot}
                  title="Telegram"
                  description={localize(lang, "Быстрые подтверждения и короткие оповещения.", "Fast approvals and short alerts.")}
                  ready={telegramReady}
                />
                <DeliveryStatusRow
                  icon={Mail}
                  title={localize(lang, "Почта", "Email")}
                  description={localize(lang, "Отчёты и подробные оповещения.", "Reports and detailed alerts.")}
                  ready={emailReady}
                />
                <DeliveryStatusRow
                  icon={ExternalLink}
                  title={localize(lang, "Внешний адрес", "Public URL")}
                  description={localize(lang, "Адрес для ссылок согласования.", "Address for approval links.")}
                  ready={siteReady}
                />
              </div>
            </div>
          </SectionCard>

          <SectionCard
            title="Telegram"
            description={localize(lang, "Быстрые подтверждения и срочные оповещения.", "Quick approvals and immediate alerts.")}
            icon={<Bot className="h-5 w-5 text-primary" />}
          >
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>{localize(lang, "Токен бота", "Bot token")}</Label>
                  <PasswordField
                    value={form.telegram_bot_token || ""}
                    onChange={(value) => setField("telegram_bot_token", value)}
                    placeholder="1234567890:AAF..."
                  />
                </div>

                <div className="space-y-2">
                  <Label>{localize(lang, "ID чата", "Chat ID")}</Label>
                  <Input
                    value={form.telegram_chat_id || ""}
                    onChange={(event) => setField("telegram_chat_id", event.target.value)}
                    placeholder="123456789"
                    className="font-mono"
                  />
                </div>

                <TestButton
                  label={localize(lang, "Отправить тест в Telegram", "Send test Telegram message")}
                  disabled={!telegramReady}
                  onTest={() => studioNotifications.testTelegram()}
                />
              </div>

              <div className="workspace-subtle rounded-2xl px-4 py-4 text-sm leading-6 text-muted-foreground">
                <p className="font-medium text-foreground">{localize(lang, "Быстрая настройка", "Quick setup")}</p>
                <p className="mt-3">{localize(lang, "1. Создайте бота через", "1. Create a bot with")} <HelpLink href="https://t.me/BotFather">@BotFather</HelpLink>.</p>
                <p>{localize(lang, "2. Запустите бота из своего Telegram-аккаунта.", "2. Start the bot from your Telegram account.")}</p>
                <p>{localize(lang, "3. Найдите ID чата через", "3. Find your chat id with")} <HelpLink href="https://t.me/userinfobot">@userinfobot</HelpLink>.</p>
              </div>
            </div>
          </SectionCard>

          <SectionCard
            title={localize(lang, "Почта", "Email")}
            description={localize(lang, "Отчёты и подробные оповещения через SMTP.", "Reports and detailed alerts over SMTP.")}
            icon={<Mail className="h-5 w-5 text-primary" />}
          >
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2 md:col-span-2">
                  <Label>{localize(lang, "Получатель", "Recipient email")}</Label>
                  <Input
                    type="email"
                    value={form.notify_email || ""}
                    onChange={(event) => setField("notify_email", event.target.value)}
                    placeholder="you@example.com"
                  />
                </div>

                <div className="space-y-2">
                  <Label>{localize(lang, "SMTP-хост", "SMTP host")}</Label>
                  <Input
                    value={form.smtp_host || ""}
                    onChange={(event) => setField("smtp_host", event.target.value)}
                    placeholder="smtp.gmail.com"
                  />
                </div>

                <div className="space-y-2">
                  <Label>{localize(lang, "SMTP-порт", "SMTP port")}</Label>
                  <Input
                    value={form.smtp_port || ""}
                    onChange={(event) => setField("smtp_port", event.target.value)}
                    placeholder="587"
                  />
                </div>

                <div className="space-y-2">
                  <Label>{localize(lang, "SMTP-пользователь", "SMTP user")}</Label>
                  <Input
                    value={form.smtp_user || ""}
                    onChange={(event) => setField("smtp_user", event.target.value)}
                    placeholder="email@example.com"
                  />
                </div>

                <div className="space-y-2">
                  <Label>{localize(lang, "SMTP-пароль", "SMTP password")}</Label>
                  <PasswordField
                    value={form.smtp_password || ""}
                    onChange={(value) => setField("smtp_password", value)}
                    placeholder={localize(lang, "Пароль приложения", "App password")}
                  />
                </div>

                <div className="space-y-2 md:col-span-2">
                  <Label>{localize(lang, "Адрес отправителя", "From address")}</Label>
                  <Input
                    value={form.from_email || ""}
                    onChange={(event) => setField("from_email", event.target.value)}
                    placeholder="WEU Platform <email@example.com>"
                  />
                </div>

                <div className="md:col-span-2">
                  <TestButton
                    label={localize(lang, "Отправить тестовое письмо", "Send test email")}
                    disabled={!emailReady}
                    onTest={() => studioNotifications.testEmail()}
                  />
                </div>
              </div>

              <div className="workspace-subtle rounded-2xl px-4 py-4 text-sm leading-6 text-muted-foreground">
                <p className="font-medium text-foreground">{localize(lang, "Заметки провайдера", "Provider notes")}</p>
                <p className="mt-3">
                  {localize(lang, "Gmail обычно требует", "Gmail usually requires an")} <HelpLink href="https://myaccount.google.com/apppasswords">{localize(lang, "пароль приложения", "app password")}</HelpLink>.
                </p>
                <p>
                  {localize(lang, "Инструкция для Yandex Mail:", "Yandex mail instructions:")}{" "}
                  <HelpLink href="https://yandex.ru/support/yandex-360/customers/mail/ru/mail-clients/others">
                    {localize(lang, "гайд по паролю приложения", "app password guide")}
                  </HelpLink>
                </p>
              </div>
            </div>
          </SectionCard>

          <SectionCard
            title={localize(lang, "Внешний адрес", "Public URL")}
            description={localize(lang, "Используется в ссылках из Telegram и писем.", "Used in links sent through Telegram and email.")}
            icon={<ExternalLink className="h-5 w-5 text-primary" />}
          >
            <div className="max-w-3xl">
              <div className="space-y-2">
                <Label>{localize(lang, "Адрес приложения", "Application URL")}</Label>
                <Input
                  value={form.site_url || ""}
                  onChange={(event) => setField("site_url", event.target.value)}
                  placeholder="https://your-server.example.com"
                />
                <p className="text-xs leading-5 text-muted-foreground">
                  {localize(lang, "Укажите адрес, доступный всем согласующим.", "Use an address all approvers can open.")}
                </p>
              </div>
            </div>
          </SectionCard>

          {isDirty ? (
            <div className="sticky bottom-4 z-20 rounded-xl border border-amber-500/30 bg-background/95 px-4 py-3 shadow-2xl backdrop-blur">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3 text-sm">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                  <div>
                    <div className="font-medium text-foreground">
                      {localize(lang, "Есть несохранённые изменения", "You have unsaved changes")}
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="outline" onClick={discardChanges} className="gap-2">
                    <RotateCcw className="h-4 w-4" />
                    {localize(lang, "Откатить", "Discard")}
                  </Button>
                  <Button type="button" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} className="gap-2">
                    {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    {localize(lang, "Сохранить изменения", "Save changes")}
                  </Button>
                </div>
              </div>
            </div>
          ) : null}
        </PageShell>
      </div>
    </div>
  );
}
