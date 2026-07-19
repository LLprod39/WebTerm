import { useCallback, useEffect, useState, type ReactNode } from "react";

import { AssistantDrawer } from "@/components/assistant/AssistantDrawer";
import { AssistantShellProvider, useAssistantShell } from "@/components/assistant/assistantContext";
import { CommandPalette } from "@/components/CommandPalette";
import { ConnectionBanner } from "@/components/ConnectionStatus";
import { HotkeyCheatsheet } from "@/components/HotkeyCheatsheet";
import { useGlobalHotkeys } from "@/hooks/use-global-hotkeys";

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

  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const openCheatsheet = useCallback(() => setCheatsheetOpen(true), []);
  const toggleAssistant = useCallback(() => assistant.toggle(), [assistant]);
  const openAssistant = useCallback(() => assistant.setOpen(true), [assistant]);

  useGlobalHotkeys({
    onOpenCommandPalette: openPalette,
    onOpenCheatsheet: openCheatsheet,
    onToggleAssistant: toggleAssistant,
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
      <HotkeyCheatsheet open={cheatsheetOpen} onOpenChange={setCheatsheetOpen} />
      <AssistantDrawer />
    </>
  );
}

export function openCommandPalette() {
  window.dispatchEvent(new CustomEvent(OPEN_PALETTE_EVENT));
}

export function openAssistantDrawer() {
  window.dispatchEvent(new CustomEvent(OPEN_ASSISTANT_EVENT));
}
