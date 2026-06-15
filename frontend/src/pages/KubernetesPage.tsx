import { Boxes } from "lucide-react";

import { EmptyState, PageHero, PageShell, SectionCard } from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";

export default function KubernetesPage() {
  const { lang } = useI18n();

  return (
    <PageShell width="full" className="space-y-5">
      <PageHero
        kicker={localize(lang, "Инфраструктура", "Infrastructure")}
        title={localize(lang, "Кубернетес", "Kubernetes")}
        description={localize(
          lang,
          "Защищенная рабочая область для будущего Kubernetes-модуля.",
          "Protected workspace for the future Kubernetes module.",
        )}
      />

      <SectionCard
        title={localize(lang, "Рабочая область", "Workspace")}
        description={localize(lang, "v1 без backend-запросов и действий.", "v1 has no backend requests or actions.")}
        icon={<Boxes className="h-4 w-4" />}
        bodyClassName="min-h-[520px]"
      >
        <EmptyState
          icon={<Boxes className="h-5 w-5" />}
          title={localize(lang, "Пустая страница", "Empty page")}
          description={localize(lang, "Kubernetes API пока не подключен.", "Kubernetes API is not connected yet.")}
          className="min-h-[420px]"
        />
      </SectionCard>
    </PageShell>
  );
}
