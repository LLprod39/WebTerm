import { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  approveExternalKubernetesAction,
  fetchAuthSession,
  fetchKubernetesActionReport,
  type KubernetesActionRequestRecord,
  type KubernetesActionTimelineEvent,
  verifyExternalKubernetesAction,
} from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { Textarea } from "@/components/ui/textarea";
import { localize } from "@/lib/i18n";

function eventLabel(lang: string, event: KubernetesActionTimelineEvent) {
  const labels: Record<string, { ru: string; en: string }> = {
    "k8s.action_request.create": { ru: "Заявка создана", en: "Request created" },
    "k8s.action_request.approve_external": { ru: "Согласовано вне WebTerm", en: "Approved outside WebTerm" },
    "k8s.action_request.verify_external": { ru: "Внешняя проверка записана", en: "External verification recorded" },
    "k8s.action_request.execute_blocked": { ru: "Выполнение заблокировано", en: "Execution blocked" },
    "k8s.action_request.rejected": { ru: "Заявка отклонена", en: "Request rejected" },
    "k8s.action_request.approval_rejected": { ru: "Согласование отклонено", en: "Approval rejected" },
    "k8s.action_request.verification_rejected": { ru: "Проверка отклонена", en: "Verification rejected" },
    "k8s.action_request.execute_rejected": { ru: "Запуск отклонён", en: "Execution rejected" },
  };
  const label = labels[event.action];
  return label ? localize(lang, label.ru, label.en) : event.action.replace(/^k8s\.action_request\./, "");
}

function actionStatusLabel(lang: string, status: string) {
  const labels: Record<string, { ru: string; en: string }> = {
    pending_approval: { ru: "ждёт согласования", en: "pending approval" },
    approved_external: { ru: "согласовано вне WebTerm", en: "approved externally" },
    verified_external: { ru: "проверено вне WebTerm", en: "verified externally" },
    rejected: { ru: "отклонено", en: "rejected" },
    blocked: { ru: "заблокировано", en: "blocked" },
    succeeded: { ru: "успешно", en: "succeeded" },
    failed: { ru: "ошибка", en: "failed" },
  };
  const label = labels[status];
  return label ? localize(lang, label.ru, label.en) : status.replaceAll("_", " ");
}

function riskTierLabel(lang: string, tier: string) {
  const labels: Record<string, { ru: string; en: string }> = {
    low: { ru: "низкий", en: "low" },
    medium: { ru: "средний", en: "medium" },
    high: { ru: "высокий", en: "high" },
    critical: { ru: "критический", en: "critical" },
  };
  const label = labels[tier];
  return label ? localize(lang, label.ru, label.en) : tier.replaceAll("_", " ");
}

function formatEventMeta(lang: string, event: KubernetesActionTimelineEvent) {
  const status = String(event.payload?.status || "");
  const approval = String(event.payload?.approval_ref || "");
  const code = String(event.payload?.code || "");
  return [status ? actionStatusLabel(lang, status) : "", approval, code].filter(Boolean).join(" · ");
}

function hasReportPayload(report?: Record<string, unknown>) {
  return Boolean(report && Object.keys(report).length > 0);
}

export function KubernetesActionRequestPanel({
  lang,
  request,
  error,
  onClose,
}: {
  lang: string;
  request: KubernetesActionRequestRecord | null;
  error: unknown;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [currentRequest, setCurrentRequest] = useState<KubernetesActionRequestRecord | null>(request);
  const [approvalRef, setApprovalRef] = useState("");
  const [approvalSummary, setApprovalSummary] = useState("");
  const [verificationOutcome, setVerificationOutcome] = useState("succeeded");
  const [verificationSummary, setVerificationSummary] = useState("");
  const [externalRef, setExternalRef] = useState("");
  const requestId = currentRequest?.id || "";
  useEffect(() => {
    setCurrentRequest(request);
    setApprovalRef(request?.approval_ref || "");
    setApprovalSummary("");
    setVerificationSummary("");
    setExternalRef("");
  }, [request?.id, request?.approval_ref, request]);
  const authQuery = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const reportQuery = useQuery({
    queryKey: ["kubernetes", "action-report", requestId],
    queryFn: () => fetchKubernetesActionReport(requestId),
    enabled: Boolean(requestId),
    staleTime: 10_000,
    retry: false,
  });
  const approveMutation = useMutation({
    mutationFn: () =>
      approveExternalKubernetesAction(requestId, {
        approval_ref: approvalRef.trim(),
        summary: approvalSummary.trim() || undefined,
      }),
    onSuccess: async (result) => {
      setCurrentRequest(result.request);
      await queryClient.invalidateQueries({ queryKey: ["kubernetes", "action-report", requestId] });
    },
  });
  const verifyMutation = useMutation({
    mutationFn: () =>
      verifyExternalKubernetesAction(requestId, {
        outcome: verificationOutcome,
        summary: verificationSummary.trim(),
        external_ref: externalRef.trim() || undefined,
      }),
    onSuccess: async (result) => {
      setCurrentRequest(result.request);
      await queryClient.invalidateQueries({ queryKey: ["kubernetes", "action-report", requestId] });
    },
  });
  const preview = currentRequest?.preview || {};
  const affected = Array.isArray(preview.affected) ? preview.affected : [];
  const verification = Array.isArray(preview.expected_verification) ? preview.expected_verification : [];
  const report = reportQuery.data;
  const timeline = report?.timeline || [];
  const isStaff = Boolean(authQuery.data?.user?.is_staff);
  const canApprove = isStaff && currentRequest?.status === "pending_approval";
  const canVerify = isStaff && currentRequest?.status === "approved_external";
  return (
    <SectionCard
      title={localize(lang, "Заявка на действие", "Action request")}
      description={localize(
        lang,
        "WebTerm создал заявку на согласование. Выполнение остаётся выключенным политикой.",
        "WebTerm created an approval request and kept execution disabled by policy.",
      )}
      icon={<RotateCcw className="h-4 w-4" />}
      actions={
        <Button variant="outline" size="sm" onClick={onClose}>
          {localize(lang, "Закрыть", "Close")}
        </Button>
      }
    >
      {error ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-4 text-sm text-destructive">
          {error instanceof Error ? error.message : localize(lang, "Не удалось создать заявку", "Failed to create request")}
        </div>
      ) : currentRequest ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="space-y-3">
            <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge label={actionStatusLabel(lang, currentRequest.status)} tone={currentRequest.status === "pending_approval" ? "warning" : "neutral"} />
                <StatusBadge label={`${localize(lang, "риск", "risk")}: ${riskTierLabel(lang, currentRequest.risk_tier)}`} tone={currentRequest.risk_tier === "high" ? "danger" : "warning"} />
                <StatusBadge
                  label={currentRequest.execution_policy.native_execution_enabled ? localize(lang, "выполнение включено", "execution on") : localize(lang, "выполнение выключено", "execution off")}
                  tone={currentRequest.execution_policy.native_execution_enabled ? "danger" : "success"}
                />
              </div>
              <h3 className="mt-3 break-all text-sm font-semibold text-foreground">{currentRequest.action}</h3>
              <div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
                <div>ID: {currentRequest.id}</div>
                <div>{localize(lang, "Кластер:", "Cluster:")} {currentRequest.cluster || "-"}</div>
                <div>{localize(lang, "Подтверждение:", "Approval:")} {currentRequest.execution_policy.approval_required ? localize(lang, "обязательно", "required") : localize(lang, "не требуется", "not required")}</div>
                <div>{localize(lang, "Предпросмотр:", "Dry-run:")} {currentRequest.execution_policy.dry_run_required ? localize(lang, "обязателен", "required") : localize(lang, "не требуется", "not required")}</div>
              </div>
            </div>

            <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
              <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">
                {localize(lang, "Проверка после подтверждения", "Verification after approval")}
              </div>
              {verification.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {verification.map((item) => (
                    <StatusBadge key={String(item)} label={String(item)} tone="neutral" />
                  ))}
                </div>
              ) : (
                <div className="mt-2 text-xs text-muted-foreground">-</div>
              )}
            </div>
            {isStaff ? (
              <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">
                    {localize(lang, "Внешнее выполнение", "External lifecycle")}
                  </div>
                  <StatusBadge label={localize(lang, "встроенное выполнение выключено", "native execute off")} tone="success" />
                </div>
                {canApprove ? (
                  <form
                    className="mt-3 space-y-3"
                    onSubmit={(event) => {
                      event.preventDefault();
                      approveMutation.mutate();
                    }}
                  >
                    <Input
                      value={approvalRef}
                      onChange={(event) => setApprovalRef(event.target.value)}
                      placeholder={localize(lang, "CHG-K8S-123 или ссылка на согласование", "CHG-K8S-123 or approval link")}
                      aria-label={localize(lang, "Ссылка на согласование", "Approval reference")}
                    />
                    <Textarea
                      value={approvalSummary}
                      onChange={(event) => setApprovalSummary(event.target.value)}
                      rows={3}
                      placeholder={localize(lang, "Кратко: кто согласовал и где будет выполнено.", "Briefly: who approved and where it will be executed.")}
                      aria-label={localize(lang, "Сводка согласования", "Approval summary")}
                    />
                    <Button size="sm" type="submit" disabled={!approvalRef.trim() || approveMutation.isPending}>
                      {approveMutation.isPending ? localize(lang, "Записываю", "Recording") : localize(lang, "Записать внешнее согласование", "Record external approval")}
                    </Button>
                  </form>
                ) : null}
                {canVerify ? (
                  <form
                    className="mt-3 space-y-3"
                    onSubmit={(event) => {
                      event.preventDefault();
                      verifyMutation.mutate();
                    }}
                  >
                    <Select value={verificationOutcome} onValueChange={setVerificationOutcome}>
                      <SelectTrigger aria-label={localize(lang, "Результат проверки", "Verification outcome")}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="succeeded">{localize(lang, "Успешно", "Succeeded")}</SelectItem>
                        <SelectItem value="failed">{localize(lang, "Неуспешно", "Failed")}</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input
                      value={externalRef}
                      onChange={(event) => setExternalRef(event.target.value)}
                      placeholder={localize(lang, "Ссылка на подтверждение в Rancher, Fleet, Devtron или GitOps", "Rancher/Fleet/Devtron/GitOps evidence link")}
                      aria-label={localize(lang, "Ссылка на внешнее подтверждение", "External evidence reference")}
                    />
                    <Textarea
                      value={verificationSummary}
                      onChange={(event) => setVerificationSummary(event.target.value)}
                      rows={3}
                      placeholder={localize(lang, "Что проверено после внешнего выполнения.", "What was verified after external execution.")}
                      aria-label={localize(lang, "Сводка проверки", "Verification summary")}
                    />
                    <Button size="sm" type="submit" disabled={!verificationSummary.trim() || verifyMutation.isPending}>
                      {verifyMutation.isPending ? localize(lang, "Записываю", "Recording") : localize(lang, "Записать внешнюю проверку", "Record external verification")}
                    </Button>
                  </form>
                ) : null}
                {!canApprove && !canVerify ? (
                  <div className="mt-3 text-xs leading-5 text-muted-foreground">
                    {localize(lang, "Следующий ручной шаг сейчас недоступен для этого статуса.", "No manual lifecycle step is available for this status.")}
                  </div>
                ) : null}
                {approveMutation.error || verifyMutation.error ? (
                  <div className="mt-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                    {(approveMutation.error || verifyMutation.error) instanceof Error
                      ? ((approveMutation.error || verifyMutation.error) as Error).message
                      : localize(lang, "Не удалось записать событие выполнения", "Failed to record lifecycle event")}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="space-y-3">
            <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
              <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">
                {localize(lang, "Затронутые объекты", "Affected objects")}
              </div>
              {affected.length ? (
                <pre className="mt-3 max-h-48 overflow-auto rounded-md bg-secondary/25 p-3 text-xs leading-5 text-foreground">
                  {JSON.stringify(affected, null, 2)}
                </pre>
              ) : (
                <div className="mt-2 text-xs text-muted-foreground">-</div>
              )}
            </div>
            <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
              <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">{localize(lang, "Политика", "Policy")}</div>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {String(currentRequest.execution_policy.blocked_reason || "")}
              </p>
            </div>
            <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">
                  {localize(lang, "Отчёт и аудит", "Report and audit")}
                </div>
                {report ? <StatusBadge label={actionStatusLabel(lang, report.status)} tone={report.status === "pending_approval" ? "warning" : "info"} /> : null}
              </div>
              {reportQuery.isLoading ? (
                <div className="mt-3 text-xs text-muted-foreground">{localize(lang, "Загружаю историю...", "Loading timeline...")}</div>
              ) : reportQuery.error ? (
                <div className="mt-3 rounded-md border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs text-amber-100">
                  {localize(lang, "Отчёт заявки пока недоступен.", "Action report is not available yet.")}
                </div>
              ) : (
                <div className="mt-3 space-y-3">
                  {timeline.length ? (
                    <div className="space-y-2">
                      {timeline.map((event, index) => (
                        <div key={`${event.action}-${event.created_at}-${index}`} className="rounded-md border border-border/60 bg-secondary/20 px-3 py-2">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="text-xs font-semibold text-foreground">{eventLabel(lang, event)}</span>
                            <span className="text-xs text-muted-foreground">{event.username || "-"}</span>
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">{event.created_at || "-"}</div>
                          {formatEventMeta(lang, event) ? <div className="mt-1 text-xs text-muted-foreground">{formatEventMeta(lang, event)}</div> : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-xs text-muted-foreground">
                      {localize(lang, "История появится после первого события аудита.", "Timeline appears after audit events.")}
                    </div>
                  )}
                  {hasReportPayload(report?.report) ? (
                    <pre className="max-h-40 overflow-auto rounded-md bg-secondary/25 p-3 text-xs leading-5 text-foreground">
                      {JSON.stringify(report?.report, null, 2)}
                    </pre>
                  ) : null}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </SectionCard>
  );
}
