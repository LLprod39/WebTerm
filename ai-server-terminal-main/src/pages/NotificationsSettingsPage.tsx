import { useEffect, useState, type ElementType } from "react";
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
  Save,
  Send,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageShell, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import { studioNotifications, type NotificationConfig } from "@/lib/api";

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
        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
        onClick={() => setVisible((current) => !current)}
        tabIndex={-1}
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
      className="inline-flex items-center gap-1 text-primary hover:underline"
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
        label={ready ? "Ready" : "Not ready"}
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
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    setResult(null);
    try {
      setResult(await onTest());
    } catch (error: unknown) {
      setResult({
        ok: false,
        message: error instanceof Error ? error.message : String(error),
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
          className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${
            result.ok
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
              : "border-red-500/30 bg-red-500/10 text-red-200"
          }`}
        >
          {result.ok ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0" /> : <AlertCircle className="h-3.5 w-3.5 shrink-0" />}
          {result.message}
        </div>
      ) : null}
    </div>
  );
}

export default function NotificationsSettingsPage() {
  const { toast } = useToast();
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

  const saveMutation = useMutation({
    mutationFn: async () => {
      await studioNotifications.save(form);
      await queryClient.invalidateQueries({ queryKey: ["studio", "notifications"] });
    },
    onSuccess: () => {
      toast({ description: "Notification settings saved." });
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
        Loading notification settings...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <StudioNav />
      <div className="flex-1 overflow-auto">
    <PageShell width="6xl">
      <SectionCard
        title="Notification settings"
        description="Studio uses these defaults for approvals, alerts, and reports."
        icon={<Bell className="h-5 w-5 text-primary" />}
        actions={
          <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} className="gap-2">
            {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save
          </Button>
        }
      >
        <div className="space-y-5">
          <div className="rounded-2xl border border-primary/20 bg-primary/5 px-4 py-4 text-sm leading-6 text-muted-foreground">
            These values act as Studio-wide defaults. Individual workflows can still override them
            when needed.
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <DeliveryStatusRow
              icon={Bot}
              title="Telegram"
              description="Fast approvals and short alerts."
              ready={telegramReady}
            />
            <DeliveryStatusRow
              icon={Mail}
              title="Email"
              description="Reports, escalation, and longer messages."
              ready={emailReady}
            />
            <DeliveryStatusRow
              icon={ExternalLink}
              title="Public URL"
              description="Approval links point here."
              ready={siteReady}
            />
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Telegram"
        description="Use Telegram for quick approvals and immediate alerts."
        icon={<Bot className="h-5 w-5 text-primary" />}
      >
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Bot token</Label>
              <PasswordField
                value={form.telegram_bot_token || ""}
                onChange={(value) => setField("telegram_bot_token", value)}
                placeholder="1234567890:AAF..."
              />
            </div>

            <div className="space-y-2">
              <Label>Chat ID</Label>
              <Input
                value={form.telegram_chat_id || ""}
                onChange={(event) => setField("telegram_chat_id", event.target.value)}
                placeholder="123456789"
                className="font-mono"
              />
            </div>

            <TestButton
              label="Send test Telegram message"
              disabled={!telegramReady}
              onTest={() => studioNotifications.testTelegram()}
            />
          </div>

          <div className="workspace-subtle rounded-2xl px-4 py-4 text-sm leading-6 text-muted-foreground">
            <p className="font-medium text-foreground">Quick setup</p>
            <p className="mt-3">1. Create a bot with <HelpLink href="https://t.me/BotFather">@BotFather</HelpLink>.</p>
            <p>2. Start the bot from your Telegram account.</p>
            <p>3. Find your chat id with <HelpLink href="https://t.me/userinfobot">@userinfobot</HelpLink>.</p>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Email"
        description="Use SMTP for reports, escalations, and links that need an audit trail."
        icon={<Mail className="h-5 w-5 text-primary" />}
      >
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2 md:col-span-2">
              <Label>Recipient email</Label>
              <Input
                type="email"
                value={form.notify_email || ""}
                onChange={(event) => setField("notify_email", event.target.value)}
                placeholder="you@example.com"
              />
            </div>

            <div className="space-y-2">
              <Label>SMTP host</Label>
              <Input
                value={form.smtp_host || ""}
                onChange={(event) => setField("smtp_host", event.target.value)}
                placeholder="smtp.gmail.com"
              />
            </div>

            <div className="space-y-2">
              <Label>SMTP port</Label>
              <Input
                value={form.smtp_port || ""}
                onChange={(event) => setField("smtp_port", event.target.value)}
                placeholder="587"
              />
            </div>

            <div className="space-y-2">
              <Label>SMTP user</Label>
              <Input
                value={form.smtp_user || ""}
                onChange={(event) => setField("smtp_user", event.target.value)}
                placeholder="email@example.com"
              />
            </div>

            <div className="space-y-2">
              <Label>SMTP password</Label>
              <PasswordField
                value={form.smtp_password || ""}
                onChange={(value) => setField("smtp_password", value)}
                placeholder="App password"
              />
            </div>

            <div className="space-y-2 md:col-span-2">
              <Label>From address</Label>
              <Input
                value={form.from_email || ""}
                onChange={(event) => setField("from_email", event.target.value)}
                placeholder="WEU Platform <email@example.com>"
              />
            </div>

            <div className="md:col-span-2">
              <TestButton
                label="Send test email"
                disabled={!emailReady}
                onTest={() => studioNotifications.testEmail()}
              />
            </div>
          </div>

          <div className="workspace-subtle rounded-2xl px-4 py-4 text-sm leading-6 text-muted-foreground">
            <p className="font-medium text-foreground">Provider notes</p>
            <p className="mt-3">
              Gmail usually requires an <HelpLink href="https://myaccount.google.com/apppasswords">app password</HelpLink>.
            </p>
            <p>
              Yandex mail instructions:{" "}
              <HelpLink href="https://yandex.ru/support/yandex-360/customers/mail/ru/mail-clients/others">
                app password guide
              </HelpLink>
            </p>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Public URL"
        description="Approval links sent by email and Telegram will point to this address."
        icon={<ExternalLink className="h-5 w-5 text-primary" />}
      >
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-2">
            <Label>Application URL</Label>
            <Input
              value={form.site_url || ""}
              onChange={(event) => setField("site_url", event.target.value)}
              placeholder="https://your-server.example.com"
            />
            <p className="text-xs leading-5 text-muted-foreground">
              Use the real external address that approvers can open from their network.
            </p>
          </div>

          <div className="workspace-subtle rounded-2xl px-4 py-4 text-sm leading-6 text-muted-foreground">
            <p className="font-medium text-foreground">How Studio uses it</p>
            <p className="mt-3">1. Email and Telegram approval links are generated from this base URL.</p>
            <p>2. If this is wrong, operators will land on a broken or local-only address.</p>
            <p>3. Keep it aligned with the actual host that serves your app.</p>
          </div>
        </div>
      </SectionCard>
    </PageShell>
  );
}
