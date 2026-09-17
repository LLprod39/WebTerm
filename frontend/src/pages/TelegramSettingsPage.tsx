import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Loader2, Plus, Trash2 } from "lucide-react";
import { MyTelegramCard } from "@/components/telegram/MyTelegramCard";
import { SettingsPageHeader } from "@/components/settings/SettingsPageHeader";
import { SettingsPageShell } from "@/components/settings/SettingsPageShell";
import { SettingsSectionCard as SectionCard } from "@/components/settings/SettingsSectionCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import { fetchAuthSession, meTelegram, type TelegramBotRecord } from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import { SettingsIcons } from "@/lib/app-icons";

function PersonalBotsSection() {
  const { lang } = useI18n();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [token, setToken] = useState("");
  const [name, setName] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [promptDraft, setPromptDraft] = useState("");

  const botsQuery = useQuery({
    queryKey: ["me", "telegram", "bots"],
    queryFn: () => meTelegram.listBots(),
  });

  const createBot = useMutation({
    mutationFn: () => meTelegram.createBot({ token, name, mode: "assistant" }),
    onSuccess: () => {
      setToken("");
      setName("");
      queryClient.invalidateQueries({ queryKey: ["me", "telegram", "bots"] });
      toast({ description: localize(lang, "Бот создан", "Bot created") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const deleteBot = useMutation({
    mutationFn: (id: number) => meTelegram.deleteBot(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me", "telegram", "bots"] });
      toast({ description: localize(lang, "Бот удалён", "Bot deleted") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const toggleBot = useMutation({
    mutationFn: ({ id, ...data }: { id: number; is_active?: boolean; system_prompt?: string }) =>
      meTelegram.updateBot(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me", "telegram", "bots"] });
      setEditingId(null);
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  return (
    <SectionCard
      title={localize(lang, "Расширенные: мои боты", "Advanced: my bots")}
      icon={Bot}
      description={localize(
        lang,
        "Свой токен BotFather — отдельный ассистент. Доступно, пока админ разрешил личные боты.",
        "Your own BotFather token — a separate assistant. Available while the admin allows personal bots.",
      )}
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>{localize(lang, "Токен бота", "Bot token")}</Label>
            <Input
              type="password"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="123456:ABC-DEF..."
            />
          </div>
          <div className="space-y-1.5">
            <Label>{localize(lang, "Имя", "Name")}</Label>
            <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="My assistant" />
          </div>
        </div>
        <Button
          type="button"
          className="gap-2"
          disabled={!token.trim() || createBot.isPending}
          onClick={() => createBot.mutate()}
        >
          {createBot.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          {localize(lang, "Добавить бота", "Add bot")}
        </Button>

        <div className="space-y-2">
          {(botsQuery.data?.bots || []).map((bot: TelegramBotRecord) => (
            <div key={bot.id} className="rounded-md border border-border px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 text-sm">
                  <div className="flex items-center gap-2 font-medium">
                    <Bot className="h-4 w-4" />
                    @{bot.bot_username || bot.name || bot.id}
                    <StatusBadge tone={bot.is_active ? "success" : "neutral"} label={bot.is_active ? "active" : "off"} />
                  </div>
                  <div className="mt-1 text-muted-foreground">
                    mode={bot.mode}
                    {bot.last_error ? ` · ${bot.last_error}` : ""}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setEditingId(editingId === bot.id ? null : bot.id);
                      setPromptDraft(bot.system_prompt || "");
                    }}
                  >
                    {localize(lang, "Промпт", "Prompt")}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => toggleBot.mutate({ id: bot.id, is_active: !bot.is_active })}
                  >
                    {bot.is_active ? localize(lang, "Выкл", "Off") : localize(lang, "Вкл", "On")}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const ok = window.confirm(
                        localize(lang, "Удалить бота? Токен будет стёрт.", "Delete bot? Token will be erased."),
                      );
                      if (ok) deleteBot.mutate(bot.id);
                    }}
                    aria-label={localize(lang, "Удалить", "Delete")}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              {editingId === bot.id ? (
                <div className="mt-3 space-y-2">
                  <Label>{localize(lang, "Системный промпт", "System prompt")}</Label>
                  <textarea
                    className="min-h-[96px] w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                    value={promptDraft}
                    onChange={(event) => setPromptDraft(event.target.value)}
                    placeholder={localize(lang, "Как ассистент должен себя вести…", "How the assistant should behave…")}
                  />
                  <Button
                    type="button"
                    size="sm"
                    disabled={toggleBot.isPending}
                    onClick={() => toggleBot.mutate({ id: bot.id, system_prompt: promptDraft })}
                  >
                    {localize(lang, "Сохранить промпт", "Save prompt")}
                  </Button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </SectionCard>
  );
}

export default function TelegramSettingsPage() {
  const { lang } = useI18n();
  const authQuery = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const statusQuery = useQuery({
    queryKey: ["me", "telegram", "status"],
    queryFn: () => meTelegram.status(),
    retry: false,
  });
  const isStaff = Boolean(authQuery.data?.user?.is_staff);
  const showPersonalBots = Boolean(statusQuery.data?.personal_bots_allowed);

  useEffect(() => {
    document.title = localize(lang, "Telegram", "Telegram");
  }, [lang]);

  return (
    <SettingsPageShell>
      <SettingsPageHeader
        icon={SettingsIcons.notifications}
        title="Telegram"
        description={localize(
          lang,
          "Подключите оповещения и ИИ-ассистента к своему аккаунту.",
          "Connect report delivery and the AI assistant to your account.",
        )}
        actions={
          isStaff ? (
            <Button asChild variant="outline" size="sm">
              <Link to="/studio/notifications">
                {localize(lang, "Токен бота платформы", "Platform bot token")}
              </Link>
            </Button>
          ) : undefined
        }
      />

      <MyTelegramCard />
      {showPersonalBots ? <PersonalBotsSection /> : null}
    </SettingsPageShell>
  );
}
