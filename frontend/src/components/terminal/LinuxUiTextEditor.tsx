import type { FrontendServer } from "@/lib/api";

import {
  TextEditorFooter,
  TextEditorHeader,
  TextEditorOpenPanel,
  TextEditorTabs,
  TextEditorWorkspace,
} from "./linux-ui-text-editor/TextEditorLayout";
import { useTextEditorController } from "./linux-ui-text-editor/useTextEditorController";

export function TextEditorWindow({
  server,
  active,
  initialPath,
  onPathConsumed,
}: {
  server: FrontendServer;
  active: boolean;
  initialPath?: string;
  onPathConsumed?: () => void;
}) {
  void active;
  const editor = useTextEditorController({ server, initialPath, onPathConsumed });

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-card text-foreground" onKeyDown={editor.handleKeyDown}>
      <TextEditorHeader
        activeTab={editor.activeTab}
        activeTabId={editor.activeTabId}
        softWrap={editor.softWrap}
        lang={editor.lang}
        onOpen={() => editor.setShowOpenDialog(true)}
        onSave={() => editor.activeTabId && void editor.saveFile(editor.activeTabId)}
        onCopyPath={() => void editor.copyPath()}
        onToggleSoftWrap={() => editor.setSoftWrap((value) => !value)}
      />

      <TextEditorTabs
        tabs={editor.tabs}
        activeTabId={editor.activeTabId}
        lang={editor.lang}
        onSelectTab={(tabId) => {
          editor.setActiveTabId(tabId);
          editor.setShowOpenDialog(false);
        }}
        onCloseTab={editor.closeTab}
        onOpen={() => editor.setShowOpenDialog(true)}
      />

      {editor.showOpenDialog ? (
        <TextEditorOpenPanel
          openPath={editor.openPath}
          recentPaths={editor.recentPaths}
          tabsCount={editor.tabs.length}
          lang={editor.lang}
          onOpenPathChange={editor.setOpenPath}
          onOpenFile={(path) => void editor.openFile(path)}
          onCancel={() => editor.setShowOpenDialog(false)}
        />
      ) : null}

      <TextEditorWorkspace
        activeTab={editor.activeTab}
        softWrap={editor.softWrap}
        textareaRef={editor.textareaRef}
        lang={editor.lang}
        onContentChange={editor.updateContent}
        onTryAnotherFile={(tab) => {
          editor.closeTab(tab.id);
          editor.setOpenPath(tab.path);
          editor.setShowOpenDialog(true);
        }}
      />

      <TextEditorFooter
        activeTab={editor.activeTab}
        activeLineCount={editor.activeLineCount}
        activeCharCount={editor.activeCharCount}
        lang={editor.lang}
        onSave={(tabId) => void editor.saveFile(tabId)}
        onReload={(tabId) => void editor.reloadFile(tabId)}
      />
    </div>
  );
}
