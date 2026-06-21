import { BookOpen, Boxes, KeyRound, Network, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { PageHero, PageShell, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";

const connectOptions = [
  {
    icon: KeyRound,
    titleRu: "Kubeconfig",
    titleEn: "Kubeconfig",
    textRu: "Загрузка файла, выбор context и scoped credentials.",
    textEn: "Upload file, choose context, and store scoped credentials.",
  },
  {
    icon: ShieldCheck,
    titleRu: "Service account",
    titleEn: "Service account",
    textRu: "Токен с namespace-scoped доступом и read-only preflight.",
    textEn: "Namespace-scoped token with read-only preflight.",
  },
  {
    icon: Network,
    titleRu: "In-cluster proxy",
    titleEn: "In-cluster proxy",
    textRu: "Локальный worker без прямого доступа браузера к Kubernetes API.",
    textEn: "Local worker without direct browser access to the Kubernetes API.",
  },
];

const roadmap = [
  { ru: "Подключение кластера и проверка доступа", en: "Cluster connection and access test" },
  { ru: "Namespaces, workloads и события", en: "Namespaces, workloads, and events" },
  { ru: "Read-only диагностика перед destructive actions", en: "Read-only diagnostics before destructive actions" },
];

export default function KubernetesPage() {
  const { lang } = useI18n();

  return (
    <PageShell width="7xl" className="space-y-5">
      <PageHero
        kicker={localize(lang, "Инфраструктура", "Infrastructure")}
        title={localize(lang, "Kubernetes beta", "Kubernetes beta")}
        description={localize(
          lang,
          "Модуль скрыт до готовности, но при включении показывает onboarding вместо пустой рабочей области.",
          "The module stays hidden until enabled, and shows onboarding instead of an empty workspace when enabled.",
        )}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={localize(lang, "Backend не подключён", "Backend not connected")} tone="warning" />
            <Button variant="outline" className="h-10 gap-2" disabled>
              <BookOpen className="h-4 w-4" />
              {localize(lang, "Документация скоро", "Docs soon")}
            </Button>
          </div>
        }
      />

      <SectionCard
        title={localize(lang, "Подключение кластера", "Connect a cluster")}
        description={localize(
          lang,
          "Первый релиз должен начинаться с безопасного подключения и проверки прав, а не с пустого canvas.",
          "The first release should start with safe connection and access checks, not a blank canvas.",
        )}
        icon={<Boxes className="h-4 w-4" />}
      >
        <div className="grid gap-3 md:grid-cols-3">
          {connectOptions.map((option) => {
            const Icon = option.icon;
            return (
              <div key={option.titleEn} className="rounded-lg border border-border/70 bg-secondary/15 p-4">
                <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 bg-background/70 text-primary">
                  <Icon className="h-4 w-4" />
                </div>
                <h3 className="text-sm font-semibold text-foreground">{localize(lang, option.titleRu, option.titleEn)}</h3>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">{localize(lang, option.textRu, option.textEn)}</p>
              </div>
            );
          })}
        </div>
      </SectionCard>

      <SectionCard
        title={localize(lang, "Roadmap до включения", "Roadmap before rollout")}
        description={localize(lang, "Что должно появиться до публичного доступа к модулю.", "What must exist before public module access.")}
        icon={<ShieldCheck className="h-4 w-4" />}
      >
        <div className="grid gap-2">
          {roadmap.map((item, index) => (
            <div key={item.en} className="flex items-start gap-3 rounded-lg border border-border/60 bg-background/45 px-4 py-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-xs font-semibold text-primary">
                {index + 1}
              </span>
              <div>
                <div className="text-sm font-medium text-foreground">{localize(lang, item.ru, item.en)}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {localize(lang, "Статус: запланировано", "Status: planned")}
                </div>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>
    </PageShell>
  );
}
