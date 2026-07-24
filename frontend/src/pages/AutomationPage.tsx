import { useCallback, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { PageShell } from "@/components/ui/page-shell";
import { PlaybooksWorkspace } from "@/pages/automation/PlaybooksWorkspace";
import {
  pathnameForPlaybooksView,
  playbooksViewFromPathname,
} from "@/pages/automation/playbookRoutes";
import type { PlaybooksView } from "@/pages/automation/playbooks/types";

export default function AutomationPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const initialView = useMemo(
    () => playbooksViewFromPathname(location.pathname),
    [location.pathname],
  );
  const onViewChange = useCallback(
    (view: PlaybooksView, options?: { replace?: boolean }) => {
      const pathname = pathnameForPlaybooksView(view);
      if (pathname !== location.pathname) navigate(pathname, { replace: options?.replace });
    },
    [location.pathname, navigate],
  );

  return (
    <PageShell width="7xl" className="space-y-4">
      <PlaybooksWorkspace initialView={initialView} onViewChange={onViewChange} />
    </PageShell>
  );
}
