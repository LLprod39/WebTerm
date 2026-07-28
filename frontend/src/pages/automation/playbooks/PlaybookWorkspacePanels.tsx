import { ChevronDown, GitBranch, KeyRound, Rocket, Settings2 } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PlaybookBindingsPanel } from "./PlaybookBindingsPanel";
import { PlaybookRevisionPanel } from "./PlaybookRevisionPanel";
import { PlaybookSharingPanel } from "./PlaybookSharingPanel";
import type { PlaybookWorkspaceVersioningController } from "./usePlaybookWorkspaceVersioning";

interface PlaybookWorkspacePanelsProps {
  lang: string;
  playbookId: number;
  workspace: PlaybookWorkspaceVersioningController;
}

export function PlaybookWorkspacePanels({ lang, playbookId, workspace }: PlaybookWorkspacePanelsProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  return (
    <details className="group overflow-hidden rounded-sm border border-border bg-card shadow-elev-1">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
        <Settings2 className="h-4 w-4 text-muted-foreground" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium text-foreground">{tr("Дополнительно", "Advanced")}</span>
          <span className="block text-xs text-muted-foreground">{tr("Версии, профили запуска и доступ", "Versions, launch profiles, and access")}</span>
        </span>
        <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <Tabs defaultValue="revisions" className="space-y-3 border-t border-border p-3">
        <TabsList aria-label={tr("Дополнительные разделы", "Advanced sections")} className="h-auto w-full justify-start overflow-x-auto">
          <TabsTrigger value="revisions" className="min-h-9 gap-1.5"><GitBranch className="h-3.5 w-3.5" />{tr("Версии", "Versions")}</TabsTrigger>
          <TabsTrigger value="bindings" className="min-h-9 gap-1.5"><Rocket className="h-3.5 w-3.5" />{tr("Запуск", "Launch")}</TabsTrigger>
          <TabsTrigger value="access" className="min-h-9 gap-1.5"><KeyRound className="h-3.5 w-3.5" />{tr("Доступ", "Access")}</TabsTrigger>
        </TabsList>
        <TabsContent value="revisions" className="m-0"><PlaybookRevisionPanel lang={lang} playbookId={playbookId} workspace={workspace} /></TabsContent>
        <TabsContent value="bindings" className="m-0"><PlaybookBindingsPanel lang={lang} workspace={workspace} /></TabsContent>
        <TabsContent value="access" className="m-0"><PlaybookSharingPanel lang={lang} workspace={workspace} /></TabsContent>
      </Tabs>
    </details>
  );
}
