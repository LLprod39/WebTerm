import { PlaybookSharingPanel } from "./PlaybookSharingPanel";
import type { PlaybookWorkspaceVersioningController } from "./usePlaybookWorkspaceVersioning";

interface PlaybookWorkspacePanelsProps {
  lang: string;
  playbookId: number;
  workspace: PlaybookWorkspaceVersioningController;
}

export function PlaybookWorkspacePanels({ lang, workspace }: PlaybookWorkspacePanelsProps) {
  return <PlaybookSharingPanel lang={lang} workspace={workspace} />;
}
