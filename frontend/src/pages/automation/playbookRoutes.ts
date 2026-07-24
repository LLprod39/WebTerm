import { matchPath } from "react-router-dom";

import type { PlaybooksView } from "./playbooks/types";

function positiveId(value: string | undefined): number | null {
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export function playbooksViewFromPathname(pathname: string): PlaybooksView {
  const runMatch = matchPath({ path: "/automation/runs/:runId", end: true }, pathname);
  const runId = positiveId(runMatch?.params.runId);
  if (runId) return { mode: "run-results", runId };

  const runWizardMatch = matchPath(
    { path: "/automation/playbooks/:playbookId/run", end: true },
    pathname,
  );
  const runPlaybookId = positiveId(runWizardMatch?.params.playbookId);
  if (runPlaybookId) return { mode: "run-wizard", playbookId: runPlaybookId };

  const playbookMatch = matchPath(
    { path: "/automation/playbooks/:playbookId", end: true },
    pathname,
  );
  const playbookId = positiveId(playbookMatch?.params.playbookId);
  if (playbookId) return { mode: "edit", playbookId };
  if (pathname === "/automation/new") return { mode: "edit", playbookId: null };
  if (pathname === "/automation/guided") return { mode: "guided" };
  return { mode: "catalog" };
}

export function pathnameForPlaybooksView(view: PlaybooksView): string {
  if (view.mode === "edit") {
    return view.playbookId ? `/automation/playbooks/${view.playbookId}` : "/automation/new";
  }
  if (view.mode === "run-wizard") return `/automation/playbooks/${view.playbookId}/run`;
  if (view.mode === "run-results") return `/automation/runs/${view.runId}`;
  if (view.mode === "guided") return "/automation/guided";
  return "/automation";
}
