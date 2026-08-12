import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import { AssistantDrawer } from "@/components/assistant/AssistantDrawer";
import { AssistantShellProvider, useAssistantShell } from "@/components/assistant/assistantContext";
import { CommandPalette } from "@/components/CommandPalette";
import { ConnectionBanner } from "@/components/ConnectionStatus";
import { HotkeyCheatsheet } from "@/components/HotkeyCheatsheet";
import { useGlobalHotkeys } from "@/hooks/use-global-hotkeys";
import { fetchAuthSession } from "@/lib/api";
import { canNavigateToPrimaryPath, canOpenAssistant } from "@/lib/navigation";

const OPEN_PALETTE_EVENT = "webterm:open-command-palette";
const OPEN_ASSISTANT_EVENT = "webterm:open-assistant";

/**
 * Global Flow chrome: command palette, hotkeys, assistant drawer, connection banner.
 * Mounted once inside authenticated AppLayout.
 */
export function FlowChrome({ children }: { children: ReactNode }) {
  return (
    <AssistantShellProvider>
      <FlowChromeInner>{children}</FlowChromeInner>
    </AssistantShellProvider>
  );
}

function FlowChromeInner({ children }: { children: ReactNode }) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [cheatsheetOpen, setCheatsheetOpen] = useState(false);
  const assistant = useAssistantShell();
  const { data: session } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const assistantEnabled = canOpenAssistant(session?.user);

  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const openCheatsheet = useCallback(() => setCheatsheetOpen(true), []);
  const toggleAssistant = useCallback(() => {
    if (assistantEnabled) assistant.toggle();
  }, [assistant, assistantEnabled]);
  const openAssistant = useCallback(() => {
    if (assistantEnabled) assistant.setOpen(true);
  }, [assistant, assistantEnabled]);

  useGlobalHotkeys({
    onOpenCommandPalette: openPalette,
    onOpenCheatsheet: openCheatsheet,
    onToggleAssistant: toggleAssistant,
    assistantEnabled,
    canNavigate: (path) => canNavigateToPrimaryPath(session?.user, path),
  });

  useEffect(() => {
    const onPalette = () => openPalette();
    const onAssistant = () => openAssistant();
    window.addEventListener(OPEN_PALETTE_EVENT, onPalette);
    window.addEventListener(OPEN_ASSISTANT_EVENT, onAssistant);
    return () => {
      window.removeEventListener(OPEN_PALETTE_EVENT, onPalette);
      window.removeEventListener(OPEN_ASSISTANT_EVENT, onAssistant);
    };
  }, [openAssistant, openPalette]);

  return (
    <>
      <ConnectionBanner />
      {children}
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onOpenAssistant={openAssistant}
      />
      <HotkeyCheatsheet
        open={cheatsheetOpen}
        onOpenChange={setCheatsheetOpen}
        canNavigate={(path) => canNavigateToPrimaryPath(session?.user, path)}
        assistantEnabled={assistantEnabled}
      />
      {assistantEnabled ? <AssistantDrawer /> : null}
    </>
  );
}

export function openCommandPalette() {
  window.dispatchEvent(new CustomEvent(OPEN_PALETTE_EVENT));
}

export function openAssistantDrawer() {
  window.dispatchEvent(new CustomEvent(OPEN_ASSISTANT_EVENT));
}
