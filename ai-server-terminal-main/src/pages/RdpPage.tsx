import { useQuery } from "@tanstack/react-query";
import { Monitor, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchFrontendBootstrap, getRdpPath } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useParams } from "react-router-dom";
import { QueryStateBlock } from "@/components/ui/page-shell";

export default function RdpPage() {
  const { lang } = useI18n();
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const { id } = useParams<{ id: string }>();
  const requestedId = Number(id || 0);

  const { data, isLoading, error } = useQuery({
    queryKey: ["frontend", "bootstrap"],
    queryFn: fetchFrontendBootstrap,
    staleTime: 20_000,
  });

  const server = data?.servers.find((item) => item.id === requestedId);

  if (isLoading || error || !server) {
    return (
      <QueryStateBlock
        loading={isLoading}
        error={error || (!isLoading && !server ? new Error(tr("RDP-сервер не найден.", "RDP server not found.")) : undefined)}
        className="p-6"
      >
        {null}
      </QueryStateBlock>
    );
  }

  return (
    <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center px-4 py-6">
      <div className="workspace-panel w-full max-w-2xl px-6 py-6 sm:px-7">
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-border/70 bg-background/40">
            <Monitor className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0 space-y-2">
            <div className="enterprise-kicker">{tr("Удалённый рабочий стол", "Remote desktop")}</div>
            <h1 className="text-2xl font-semibold tracking-[-0.04em] text-foreground">{server.name}</h1>
            <p className="text-sm leading-6 text-muted-foreground">
              {tr(
                "RDP-сессия открывается через отдельную legacy-страницу. Здесь оставлен только понятный handoff без лишних кнопок и пустого интерфейса.",
                "The RDP session opens through a separate legacy page. This screen is only a clear handoff without extra buttons or empty chrome.",
              )}
            </p>
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <div className="workspace-subtle rounded-2xl px-4 py-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              {tr("Хост", "Host")}
            </div>
            <div className="mt-2 font-mono text-sm text-foreground">
              {server.host}:{server.port}
            </div>
            <div className="mt-2 text-xs leading-5 text-muted-foreground">{server.username}</div>
          </div>

          <div className="workspace-subtle rounded-2xl px-4 py-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              {tr("Что дальше", "Next step")}
            </div>
            <div className="mt-2 text-sm leading-6 text-muted-foreground">
              {tr(
                "Откройте полноценную RDP-страницу. После перехода весь дальнейший поток идёт уже там.",
                "Open the full RDP page. After that, the rest of the flow continues there.",
              )}
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Button onClick={() => (window.location.href = getRdpPath(server.id))} className="gap-2">
            <ExternalLink className="h-4 w-4" />
            {tr("Открыть RDP", "Open RDP")}
          </Button>
          <Button variant="outline" onClick={() => window.history.back()}>
            {tr("Назад", "Back")}
          </Button>
        </div>

        <p className="mt-4 text-xs leading-5 text-muted-foreground">
          {tr(
            "Если открывать RDP нужно сразу без этого шага, следующим проходом можно сделать автопереход после короткого подтверждения.",
            "If you want RDP to open immediately without this step, the next pass can switch this screen to an auto-redirect after a short confirmation.",
          )}
        </p>
      </div>
    </div>
  );
}
