import { useCallback, useState } from "react";

import {
  clearMasterPassword,
  getMasterPasswordStatus,
  revealServerPassword,
  setMasterPassword as saveMasterPassword,
  type FrontendServer,
} from "@/lib/api";

type Translate = (key: string) => string;

export function useServerSecurityController(activeServer: FrontendServer | null, t: Translate) {
  const [masterPassword, setMasterPasswordText] = useState("");
  const [hasMasterPassword, setHasMasterPassword] = useState(false);
  const [revealedPassword, setRevealedPassword] = useState("");

  const resetForAdvancedOpen = useCallback(() => {
    setRevealedPassword("");
  }, []);

  const loadMasterPasswordStatus = useCallback(async () => {
    try {
      const status = await getMasterPasswordStatus();
      setHasMasterPassword(Boolean(status.has_master_password));
      return status;
    } catch {
      const fallback = { has_master_password: false };
      setHasMasterPassword(false);
      return fallback;
    }
  }, []);

  const onSetMasterPassword = useCallback(async () => {
    if (!masterPassword.trim()) return;
    await saveMasterPassword(masterPassword.trim());
    setHasMasterPassword(true);
    alert(t("srv.master_pw_saved"));
  }, [masterPassword, t]);

  const onClearMasterPassword = useCallback(async () => {
    await clearMasterPassword();
    setHasMasterPassword(false);
    alert(t("srv.master_pw_cleared"));
  }, [t]);

  const onRevealPassword = useCallback(async () => {
    if (!activeServer) return;
    const response = await revealServerPassword(activeServer.id, masterPassword.trim());
    if (response.success) setRevealedPassword(response.password || "");
    else alert(response.error || t("srv.reveal_failed"));
  }, [activeServer, masterPassword, t]);

  return {
    hasMasterPassword,
    loadMasterPasswordStatus,
    masterPassword,
    onClearMasterPassword,
    onRevealPassword,
    onSetMasterPassword,
    resetForAdvancedOpen,
    revealedPassword,
    setMasterPasswordText,
  };
}

export type ServerSecurityController = ReturnType<typeof useServerSecurityController>;
