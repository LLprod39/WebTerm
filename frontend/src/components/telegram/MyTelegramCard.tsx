import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  Link2,
  Loader2,
  Save,
  Send,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import {
  meTelegram,
  myNotifications,
  type MyNotificationPrefs,
  type TelegramLinkCodeResponse,
  type TelegramStatus,
} from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";

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
          onTest()
            .then((response) => setResult({ ...response, testedAt: new Date() }))
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

function HubBanner({ status }: { status?: TelegramStatus }) {
  const { lang } = useI18n();
  if (!status || status.hub_hint === "ok") return null;
  return (
    <div className="flex items-start gap-2 rounded-sm border border-warning/30 bg-warning/5 px-3 py-2 text-sm text-foreground">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
      <p>
        {localize(
          lang,
          "Воркер telegram-bot, похоже, не запущен: /start и ответы ИИ не придут, пока админ не поднимет hub. Отчёты по chat ID могут работать.",
          "The telegram-bot worker looks offline: /start and AI replies need the hub. Report delivery by chat ID may still work.",
        )}
      </p>
    </div>
  );
}

export function MyTelegramCard({ className }: { className?: string }) {
  const { lang } = useI18n();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<MyNotificationPrefs>({ telegram_chat_id: "", telegram_enabled: true });
  const [manualOpen, setManualOpen] = useState(false);
  const [codePayload, setCodePayload] = useState<TelegramLinkCodeResponse | null>(null);

  const statusQuery = useQuery({
    queryKey: ["me", "telegram", "status"],
    queryFn: () => meTelegram.status(),
    refetchInterval: 15_000,
  });

  const prefsQuery = useQuery({
    queryKey: ["me", "notifications"],
    queryFn: myNotifications.get,
  });

  useEffect(() => {
    if (!prefsQuery.data) return;
    setForm({
      telegram_chat_id: prefsQuery.data.telegram_chat_id || "",
      telegram_enabled: prefsQuery.data.telegram_enabled !== false,
    });
  }, [prefsQuery.data]);

  const isDirty =
    (prefsQuery.data?.telegram_chat_id || "") !== (form.telegram_chat_id || "")
    || Boolean(prefsQuery.data?.telegram_enabled !== false) !== Boolean(form.telegram_enabled);

  const saveMutation = useMutation({
    mutationFn: () => myNotifications.save(form),
    onSuccess: async (saved) => {
      setForm({
        telegram_chat_id: saved.telegram_chat_id || "",
        telegram_enabled: saved.telegram_enabled !== false,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["me", "notifications"] }),
        queryClient.invalidateQueries({ queryKey: ["me", "telegram", "status"] }),
      ]);
      toast({ description: localize(lang, "Личный Telegram сохранён.", "Personal Telegram saved.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const createCode = useMutation({
    mutationFn: () => meTelegram.createLinkCode(),
    onSuccess: (data) => {
      setCodePayload(data);
      toast({ description: localize(lang, "Код привязки создан", "Link code created") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const deleteLink = useMutation({
    mutationFn: (id: number) => meTelegram.deleteLink(id),
    onSuccess: async () => {
      setCodePayload(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["me", "telegram"] }),
        queryClient.invalidateQueries({ queryKey: ["me", "notifications"] }),
      ]);
      toast({
        description: localize(
          lang,
          "Привязка ИИ снята. Отчёты могут продолжать идти на сохранённый chat ID.",
          "AI link removed. Reports may still go to the saved chat ID.",
        ),
      });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const status = statusQuery.data;
  const canNotifications = status?.notifications_allowed !== false;
  const canAssistant = Boolean(status?.assistant_allowed);
  const linked = Boolean(status?.linked);
  const personalReady = Boolean(form.telegram_enabled && (form.telegram_chat_id.trim() || status?.chat_id));
  const botLabel = status?.bot_username ? `@${status.bot_username}` : localize(lang, "бот платформы", "platform bot");
  const isLoading = statusQuery.isLoading || prefsQuery.isLoading;

  return (
    <SectionCard
      title={localize(lang, "Мой Telegram", "My Telegram")}
      description={localize(
        lang,
        "Оповещения и ИИ-ассистент на боте платформы — один аккаунт, один клик «Подключить».",
        "Reports and the AI assistant on the platform bot — one account, one Connect click.",
      )}
      className={className}
      actions={
        canNotifications ? (
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || !isDirty || isLoading}
            className="gap-2"
          >
            {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : isDirty ? <Save className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
            {isDirty ? localize(lang, "Сохранить", "Save") : localize(lang, "Сохранено", "Saved")}
          </Button>
        ) : null
      }
    >
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {localize(lang, "Загружаю…", "Loading…")}
        </div>
      ) : (
        <div className="space-y-5">
          <HubBanner status={status} />

          {!status?.bot_configured ? (
            <div className="flex items-start gap-2 rounded-sm border border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <p>
                {localize(
                  lang,
                  "Админ ещё не задал токен бота платформы (Studio → Оповещения).",
                  "An admin has not set the platform bot token yet (Studio → Notifications).",
                )}
              </p>
            </div>
          ) : null}

          {canNotifications ? (
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-foreground">
                {localize(lang, "Оповещения", "Notifications")}
              </h3>
              <label className="flex items-center gap-2 text-sm text-foreground">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-border"
                  checked={form.telegram_enabled}
                  onChange={(event) => setForm((current) => ({ ...current, telegram_enabled: event.target.checked }))}
                />
                {localize(lang, "Получать отчёты в Telegram", "Receive reports in Telegram")}
              </label>
              <div className="flex flex-wrap items-center gap-3">
                <StatusBadge
                  tone={personalReady ? "success" : "warning"}
                  label={
                    personalReady
                      ? localize(lang, "Готово к доставке", "Ready for delivery")
                      : localize(lang, "Нужен chat ID или привязка", "Need chat ID or link")
                  }
                />
                {status?.chat_id ? (
                  <span className="font-mono text-xs text-muted-foreground">chat {status.chat_id}</span>
                ) : null}
              </div>
            </div>
          ) : null}

          <div className="space-y-3 border-t border-border pt-4">
            <h3 className="text-sm font-medium text-foreground">
              {localize(lang, "ИИ-ассистент", "AI assistant")}
            </h3>
            {canAssistant ? (
              <>
                <p className="text-sm text-muted-foreground">
                  {linked
                    ? localize(
                        lang,
                        `Привязан к ${botLabel}. Пишите боту в Telegram — он ответит как ассистент платформы.`,
                        `Linked to ${botLabel}. Message the bot in Telegram — it replies as the platform assistant.`,
                      )
                    : localize(
                        lang,
                        "Подключите аккаунт через бота — отчёты и ИИ заработают вместе.",
                        "Connect via the bot — reports and AI will work together.",
                      )}
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  {!linked ? (
                    <Button
                      type="button"
                      onClick={() => createCode.mutate()}
                      disabled={createCode.isPending || !status?.bot_configured}
                      className="gap-2"
                    >
                      {createCode.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
                      {localize(lang, "Подключить Telegram", "Connect Telegram")}
                    </Button>
                  ) : (
                    <>
                      <StatusBadge tone="success" label={localize(lang, "Привязан", "Linked")} />
                      {status?.bot_username ? (
                        <a
                          href={`https://t.me/${status.bot_username}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-sm text-primary underline"
                        >
                          {localize(lang, "Написать боту", "Message bot")}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : null}
                      {status?.link?.id ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => deleteLink.mutate(status.link!.id)}
                          disabled={deleteLink.isPending}
                        >
                          {localize(lang, "Отвязать ИИ", "Unlink AI")}
                        </Button>
                      ) : null}
                    </>
                  )}
                </div>
                {codePayload ? (
                  <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
                    <p>
                      {localize(lang, "Код", "Code")}: <code className="font-mono">{codePayload.code}</code>
                    </p>
                    {codePayload.deep_link ? (
                      <p className="mt-2">
                        <a
                          href={codePayload.deep_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary underline"
                        >
                          {localize(lang, "Открыть бота в Telegram", "Open bot in Telegram")}
                        </a>
                      </p>
                    ) : (
                      <p className="mt-2 text-muted-foreground">
                        {localize(
                          lang,
                          "Отправьте боту команду /start с этим кодом.",
                          "Send /start with this code to the bot.",
                        )}
                      </p>
                    )}
                    <p className="mt-1 text-xs text-muted-foreground">
                      {localize(lang, "Истекает", "Expires")}: {codePayload.expires_at}
                    </p>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                {localize(
                  lang,
                  "Нет доступа к ИИ в Telegram (нужны chat и telegram_assistant, плюс флаг ассистента у админа).",
                  "No Telegram AI access (need chat + telegram_assistant, plus the admin assistant flag).",
                )}
              </p>
            )}
          </div>

          {canNotifications ? (
            <Collapsible open={manualOpen} onOpenChange={setManualOpen}>
              <CollapsibleTrigger asChild>
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-2 border-t border-border pt-4 text-left text-sm font-medium text-foreground"
                >
                  <span>
                    {localize(lang, "Только отчёты: chat ID вручную", "Reports only: enter chat ID")}
                  </span>
                  <ChevronDown className={`h-4 w-4 transition-transform ${manualOpen ? "rotate-180" : ""}`} />
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-3 pt-3">
                <p className="text-sm text-muted-foreground">
                  {localize(
                    lang,
                    "Если ИИ не нужен или hub недоступен — укажите chat ID через",
                    "If you only need reports or the hub is down — get your chat ID via",
                  )}{" "}
                  <HelpLink href="https://t.me/userinfobot">@userinfobot</HelpLink>.
                </p>
                <div className="space-y-2">
                  <Label>{localize(lang, "Мой chat ID", "My chat ID")}</Label>
                  <Input
                    value={form.telegram_chat_id}
                    onChange={(event) => setForm((current) => ({ ...current, telegram_chat_id: event.target.value }))}
                    placeholder="123456789"
                    className="font-mono"
                    disabled={!form.telegram_enabled}
                  />
                </div>
                <TestButton
                  label={localize(lang, "Отправить мне тест", "Send me a test")}
                  disabled={!form.telegram_chat_id.trim()}
                  onTest={() => myNotifications.testTelegram(form.telegram_chat_id.trim())}
                />
                {linked && form.telegram_chat_id.trim() ? (
                  <p className="text-xs text-muted-foreground">
                    {localize(
                      lang,
                      "После отвязки ИИ отчёты продолжат идти на этот chat ID, пока он сохранён.",
                      "After unlinking AI, reports keep using this chat ID while it is saved.",
                    )}
                  </p>
                ) : null}
              </CollapsibleContent>
            </Collapsible>
          ) : null}
        </div>
      )}
    </SectionCard>
  );
}
