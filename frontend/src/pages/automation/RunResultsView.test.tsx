import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getPlaybookRunReport,
  getPlaybookRunReportHost,
  getPlaybookRunReportLog,
  type PlaybookRun,
  type PlaybookRunReport,
} from "@/api/playbooks";
import { RunResultsView } from "./RunResultsView";

vi.mock("@/api/playbooks", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/playbooks")>();
  return {
    ...original,
    getPlaybookRunReport: vi.fn(),
    getPlaybookRunReportHost: vi.fn(),
    getPlaybookRunReportLog: vi.fn(),
    getPlaybookRunRetryContext: vi.fn(),
    downloadPlaybookRunReport: vi.fn(),
  };
});

const run = {
  id: 91,
  playbook_id: 7,
  status: "completed",
  playbook_name: "Health snapshot",
  target_server_ids: [12],
  target_group_ids: [],
  options: { dry_run: true },
  summary: { hosts_total: 1, hosts_ok: 1, hosts_failed: 0, tasks_ok: 2, tasks_failed: 0 },
  inventory_preview: "",
  error_message: "",
  cancel_requested: false,
  started_at: "2026-08-26T10:00:00Z",
  finished_at: "2026-08-26T10:00:11Z",
  created_at: "2026-08-26T09:59:59Z",
  live_log: "PLAY [Health snapshot]\n",
  host_results: [],
} as PlaybookRun;

const report = {
  schema_version: 2,
  run: {
    id: 91,
    playbook_id: 7,
    playbook_name: "Health snapshot",
    revision_id: 14,
    validation_id: 77,
    binding_profile_id: null,
    binding_profile_name: "",
    status: "completed",
    cancel_requested: false,
    target_count: 1,
    options: { dry_run: true },
    created_at: run.created_at,
    started_at: run.started_at,
    finished_at: run.finished_at,
    duration_ms: 11_000,
  },
  progress: {
    state_version: 3,
    phase: "completed",
    total_kind: "exact",
    completed: 2,
    total: 2,
    percent: 100,
    indeterminate: false,
    engine: "ansible",
    play: "Health snapshot",
    task: "",
    task_number: 2,
    hosts_seen: 1,
    hosts_total: 1,
    counts: { ok: 2 },
    is_terminal: true,
    log_start_cursor: 0,
    log_end_cursor: 24,
    log_truncated: false,
  },
  summary: run.summary,
  failure: null,
  hosts: [{
    server_id: 12,
    server_name: "web-01",
    host: "10.0.0.12",
    status: "success",
    task_counts: { total: 2, ok: 2, changed: 0, failed: 0, unreachable: 0, skipped: 0, cancelled: 0, running: 0, pending: 0 },
    first_failure: null,
    detail_url: "/servers/api/playbooks/runs/91/hosts/12/",
  }],
  dispatch: null,
  log: { start_cursor: 0, end_cursor: 24, truncated: false, url: "/servers/api/playbooks/runs/91/log/" },
  actions: { can_cancel: false, can_retry_failed: false, can_export: true, retry_context_url: "/retry/", export_url: "/export/" },
} as PlaybookRunReport;

function LocationProbe() {
  return <output aria-label="location">{useLocation().search}</output>;
}

function renderView(activeRun: PlaybookRun = run) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/automation/runs/${activeRun.id}`]}>
        <RunResultsView lang="en" run={activeRun} onBack={vi.fn()} onCancel={vi.fn()} onRerunFailed={vi.fn()} />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RunResultsView report workspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getPlaybookRunReport).mockResolvedValue({ success: true, report });
    vi.mocked(getPlaybookRunReportHost).mockResolvedValue({
      success: true,
      host: { ...report.hosts[0], tasks: [{ task_id: "gather", name: "Gather facts", command: "setup", description: "", status: "success", exit_code: 0, output: "ok" }] },
    });
    vi.mocked(getPlaybookRunReportLog).mockResolvedValue({ success: true, text: "PLAY [Health snapshot]\n", cursor: 0, next_cursor: 24, start_cursor: 0, end_cursor: 24, has_more: false, truncated: false, reset_required: false });
  });

  it("keeps report sections in the URL and loads heavy data only on demand", async () => {
    renderView();
    expect(await screen.findByRole("tab", { name: "Result", selected: true })).toBeInTheDocument();
    expect(screen.getByText("1/1")).toBeInTheDocument();
    expect(getPlaybookRunReportHost).not.toHaveBeenCalled();
    expect(getPlaybookRunReportLog).not.toHaveBeenCalled();

    fireEvent.mouseDown(screen.getByRole("tab", { name: /Execution/ }), { button: 0, ctrlKey: false });
    await waitFor(() => expect(screen.getByLabelText("location")).toHaveTextContent("?tab=execution"));
    fireEvent.click(await screen.findByRole("button", { name: /web-01/i }));
    await waitFor(() => expect(getPlaybookRunReportHost).toHaveBeenCalledWith(91, 12));
    expect(await screen.findByText("Gather facts")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Log" }), { button: 0, ctrlKey: false });
    await waitFor(() => expect(screen.getByLabelText("location")).toHaveTextContent("?tab=log"));
    await waitFor(() => expect(getPlaybookRunReportLog).toHaveBeenCalledWith(91, 0));
    expect(await screen.findByText(/PLAY \[Health snapshot\]/)).toBeInTheDocument();
  });

  it("opens a live run on Execution and labels estimated progress without presenting it as exact", async () => {
    const runningRun = {
      ...run,
      status: "running",
      finished_at: null,
      progress: { phase: "executing", task: "Configure service", finished: false },
    } as PlaybookRun;
    const estimatedReport = {
      ...report,
      run: { ...report.run, status: "running", finished_at: null, binding_profile_id: 8, binding_profile_name: "Production checks" },
      progress: {
        ...report.progress,
        phase: "executing",
        task: "Configure service",
        total_kind: "estimated",
        completed: 3,
        total: 10,
        percent: 30,
        indeterminate: false,
        is_terminal: false,
      },
      actions: { ...report.actions, can_cancel: true, can_export: false },
    } as PlaybookRunReport;
    vi.mocked(getPlaybookRunReport).mockResolvedValue({ success: true, report: estimatedReport });

    renderView(runningRun);

    expect(await screen.findByRole("tab", { name: /Execution/, selected: true })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("location")).toHaveTextContent("?tab=execution"));
    expect(await screen.findByText("≈ 3 of 10")).toBeInTheDocument();
    const progressbar = screen.getByRole("progressbar");
    expect(progressbar).not.toHaveAttribute("aria-valuenow");
    expect(progressbar).toHaveAttribute("aria-valuetext", "Approximately 3 of 10 complete");
    expect(screen.getByText(/profile Production checks/)).toBeInTheDocument();
  });
});
