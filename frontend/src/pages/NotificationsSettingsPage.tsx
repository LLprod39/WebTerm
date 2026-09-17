import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { StudioNav } from "@/components/StudioNav";
import { MyTelegramCard } from "@/components/telegram/MyTelegramCard";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  ExternalLink,
  Eye,
  EyeOff,
  Loader2,
  RotateCcw,
  Save,
  Send,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageShell, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import { studioNotifications, studioTelegram, type NotificationConfig } from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";

function normalizePlatformTelegram(config?: Partial<NotificationConfig>) {
  return {
    telegram_bot_token: String(config?.telegram_bot_token ?? ""),
    telegram_chat_id: String(config?.telegram_chat_id ?? ""),
    telegram_assistant_enabled: config?.telegram_assistant_enabled !== false,
    telegram_personal_bots_enabled: config?.telegram_personal_bots_enabled !== false,
  };
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

function TestButton({
  label,
  disabled,
  onTest,
}: {
  label: string;
  disabled?: boolean;
  onTest: () => Promise<{ ok: boolean; message: string }>;
}) {
  const { lang } = useI18n();
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string; testedAt: Date } | null>(null);

  return (
    <div className="space-y-2">
      <Button
        type="button"
        variant="outline"
        className="gap-2"
        disabled={disabled || pending}
        onClick={() => {
          setPending(true);
          setResult(null);
          void onTest()
            .then((response) => setResult({ ok: true, message: response.message, testedAt: new Date() }))
            .catch((error: Error) => setResult({ ok: false, message: error.message, testedAt: new Date() }))
            .finally(() => setPending(false));
        }}
      >
        {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        {label}
      </Button>
      {result ? (
        <div className={`flex items-start gap-2 text-sm ${result.ok ? "text-success" : "text-destructive"}`}>
          {result.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />}
          <span>
            <span className="block">{result.message}</span>
            <span className="mt-0.5 block text-muted-foreground">
              {localize(lang, "Проверено", "Tested")}{" "}
              {result.testedAt.toLocaleTimeString(lang === "ru" ? "ru-RU" : "en-US", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </span>
        </div>
      ) : null}
    </div>
  );
}

function PlatformBotSection() {
  const { toast } = useToast();
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(normalizePlatformTelegram());

  const { data: config, isLoading, isError } = useQuery({
    queryKey: ["studio", "notifications"],
    queryFn: studioNotifications.get,
    retry: false,
  });

  const botsQuery = useQuery({
    queryKey: ["studio", "telegram", "bots"],
    queryFn: studioTelegram.listBots,
    retry: false,
  });

  useEffect(() => {
    if (!config) return;
    setForm(normalizePlatformTelegram(config));
  }, [config]);

  const isDirty = JSON.stringify(normalizePlatformTelegram(config)) !== JSON.stringify(form);
  const discardChanges = () => {
    if (!config) return;
    setForm(normalizePlatformTelegram(config));
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      await studioNotifications.save(form);
      return form;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["studio", "notifications"] });
      await queryClient.invalidateQueries({ queryKey: ["studio", "telegram", "bots"] });
      toast({ description: localize(lang, "Бот платформы сохранён.", "Platform bot saved.") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const toggleBot = useMutation({
    mutationFn: ({ id, ...data }: { id: number; is_active?: boolean; mode?: string }) =>
      studioTelegram.updateBot(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["studio", "telegram", "bots"] }),
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const botReady = Boolean(form.telegram_bot_token.trim());
  const fallbackReady = Boolean(form.telegram_bot_token.trim() && form.telegram_chat_id.trim());

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {localize(lang, "Загружаю бота платформы…", "Loading platform bot…")}
      </div>
    );
  }

  return (
    <>
      <SectionCard
        title={localize(lang, "Бот платформы", "Platform bot")}
        description={localize(
          lang,
          "Общий токен BotFather. Пользователи подключают его себе в Настройки → Telegram.",
          "Shared BotFather token. Users connect it in Settings → Telegram.",
        )}
        icon={<Bot className="h-5 w-5 text-primary" />}
        actions={
          <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending || !isDirty || isError} className="gap-2">
            {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : isDirty ? <Save className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
            {isDirty ? localize(lang, "Сохранить бота", "Save bot") : localize(lang, "Сохранено", "Saved")}
          </Button>
        }
      >
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>{localize(lang, "Токен бота", "Bot token")}</Label>
              <PasswordField
                value={form.telegram_bot_token}
                onChange={(value) => setForm((current) => ({ ...current, telegram_bot_token: value }))}
                placeholder="1234567890:AAF..."
              />
            </div>

            <div className="space-y-2">
              <Label>{localize(lang, "Chat ID по умолчанию (fallback)", "Default chat ID (fallback)")}</Label>
              <Input
                value={form.telegram_chat_id}
                onChange={(event) => setForm((current) => ({ ...current, telegram_chat_id: event.target.value }))}
                placeholder="123456789"
                className="font-mono"
              />
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.telegram_assistant_enabled}
                onChange={(event) =>
                  setForm((current) => ({ ...current, telegram_assistant_enabled: event.target.checked }))
                }
              />
              {localize(lang, "Режим ИИ-ассистента для platform-бота", "AI assistant mode for platform bot")}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.telegram_personal_bots_enabled}
                onChange={(event) =>
                  setForm((current) => ({ ...current, telegram_personal_bots_enabled: event.target.checked }))
                }
              />
              {localize(lang, "Разрешить личные боты пользователей", "Allow personal user bots")}
            </label>

            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge
                tone={botReady ? "success" : "warning"}
                label={botReady ? localize(lang, "Бот задан", "Bot set") : localize(lang, "Нужен токен", "Token needed")}
              />
              <TestButton
                label={localize(lang, "Тест на fallback chat", "Test fallback chat")}
                disabled={!fallbackReady}
                onTest={() => studioNotifications.testTelegram()}
              />
            </div>
          </div>

          <div className="workspace-subtle rounded-sm px-4 py-4 text-sm leading-6 text-muted-foreground">
            <p className="font-medium text-foreground">{localize(lang, "Для админа", "For admins")}</p>
            <p className="mt-3">
              {localize(lang, "1. Создайте бота через", "1. Create a bot with")}{" "}
              <HelpLink href="https://t.me/BotFather">@BotFather</HelpLink>.
            </p>
            <p>{localize(lang, "2. Вставьте token сюда.", "2. Paste the token here.")}</p>
            <p>
              {localize(lang, "3. Личные настройки каждого пользователя:", "3. Each user’s personal setup:")}{" "}
              <Link to="/settings/telegram" className="font-medium text-primary underline">
                {localize(lang, "Настройки → Telegram", "Settings → Telegram")}
              </Link>
              .
            </p>
            <p className="mt-3">
              {localize(
                lang,
                "Без воркера telegram-bot /start и ИИ не работают; доставка отчётов по chat ID может.",
                "Without the telegram-bot worker, /start and AI fail; report delivery by chat ID may still work.",
              )}
            </p>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title={localize(lang, "Все боты", "All bots")}
        description={localize(lang, "Platform и личные боты. Можно деактивировать.", "Platform and personal bots. You can deactivate them.")}
        className="mt-6"
      >
        <div className="space-y-2">
          {(botsQuery.data?.bots || []).map((bot) => (
            <div key={bot.id} className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm">
              <div className="min-w-0">
                <div className="font-medium">
                  {bot.kind} · @{bot.bot_username || bot.name || bot.id} · {bot.mode}
                </div>
                <div className="text-muted-foreground">
                  {bot.is_active ? "active" : "off"}
                  {bot.last_error ? ` · ${bot.last_error}` : ""}
                </div>
              </div>
              <div className="flex shrink-0 gap-1">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  title={localize(lang, "Переключить режим", "Switch mode")}
                  onClick={() =>
                    toggleBot.mutate({ id: bot.id, mode: bot.mode === "assistant" ? "pipeline" : "assistant" })
                  }
                >
                  {bot.mode === "assistant"
                    ? localize(lang, "→ pipeline", "→ pipeline")
                    : localize(lang, "→ ассистент", "→ assistant")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => toggleBot.mutate({ id: bot.id, is_active: !bot.is_active })}
                >
                  {bot.is_active ? localize(lang, "Выкл", "Off") : localize(lang, "Вкл", "On")}
                </Button>
              </div>
            </div>
          ))}
          {!botsQuery.isLoading && !(botsQuery.data?.bots || []).length ? (
            <p className="text-sm text-muted-foreground">{localize(lang, "Ботов пока нет.", "No bots yet.")}</p>
          ) : null}
        </div>
      </SectionCard>

      {isDirty ? (
        <div className="sticky bottom-4 z-20 rounded-sm border border-warning/30 bg-card px-4 py-3 shadow-elev-2">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3 text-sm">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
              <div className="font-medium text-foreground">
                {localize(lang, "Есть несохранённые изменения бота", "Unsaved bot changes")}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={discardChanges} className="h-10 gap-2 rounded-sm">
                <RotateCcw className="h-4 w-4" aria-hidden />
                {localize(lang, "Откатить", "Discard")}
              </Button>
              <Button type="button" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} className="h-10 gap-2 rounded-sm">
                {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Save className="h-4 w-4" aria-hidden />}
                {localize(lang, "Сохранить", "Save")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

/**
 * Settings (`variant=personal`): My Telegram card.
 * Studio (`variant=platform`): platform bot only + link to personal settings.
 */
export default function NotificationsSettingsPage({
  showStudioNav = true,
  variant,
  embedded = false,
}: {
  showStudioNav?: boolean;
  /** personal = settings (user); platform = studio (admin bot) */
  variant?: "personal" | "platform";
  /** When true, skip outer page chrome (legacy embed). */
  embedded?: boolean;
}) {
  const mode = variant ?? (showStudioNav ? "platform" : "personal");
  const { lang } = useI18n();

  const body =
    mode === "personal" ? (
      <>
        {!embedded ? (
          <div className="mb-1">
            <h1 className="font-display text-xl font-semibold text-foreground">
              {localize(lang, "Оповещения", "Notifications")}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {localize(lang, "Подключите Telegram к своему аккаунту.", "Connect Telegram to your account.")}
            </p>
          </div>
        ) : null}
        <MyTelegramCard className={embedded ? "mt-4" : undefined} />
      </>
    ) : (
      <>
        <div className="mb-1">
          <h1 className="font-display text-xl font-semibold text-foreground">
            {localize(lang, "Оповещения Studio", "Studio notifications")}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {localize(
              lang,
              "Токен и флаги бота платформы. Личные оповещения и ИИ — в Настройки → Telegram.",
              "Platform bot token and flags. Personal reports and AI live in Settings → Telegram.",
            )}
          </p>
        </div>
        <PlatformBotSection />
        <SectionCard
          title={localize(lang, "Личные настройки", "Personal settings")}
          description={localize(
            lang,
            "Подключить свой Telegram к отчётам и ИИ можно здесь:",
            "Connect your Telegram for reports and AI here:",
          )}
          className="mt-6"
        >
          <Link
            to="/settings/telegram"
            className="inline-flex items-center gap-1 text-sm font-medium text-primary underline"
          >
            {localize(lang, "Открыть Настройки → Telegram", "Open Settings → Telegram")}
            <ExternalLink className="h-3 w-3" />
          </Link>
        </SectionCard>
      </>
    );

  if (embedded) {
    return <div className="mt-4">{body}</div>;
  }

  return (
    <div className="flex h-full flex-col">
      {showStudioNav ? <StudioNav /> : null}
      <div className="flex-1 overflow-auto">
        <PageShell width="6xl">{body}</PageShell>
      </div>
    </div>
  );
}
