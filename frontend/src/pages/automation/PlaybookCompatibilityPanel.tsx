import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, CheckCircle2, RefreshCw, ShieldCheck } from "lucide-react";
import {
  adaptPlaybookCompatibility,
  adaptPlaybookSource,
  analyzePlaybookCompatibility,
  analyzePlaybookSource,
  applyPlaybookCompatibility,
  type PlaybookCompatibilityBase,
  type PlaybookCompatibilityReport,
  type PlaybookDetail,
} from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { notify } from "@/lib/notify";
import { cn } from "@/lib/utils";

interface PlaybookCompatibilityPanelProps {
  lang: string;
  playbookId: number | null;
  sourcePath?: string;
  sourceYaml: string;
  report?: PlaybookCompatibilityReport;
  canAdapt?: boolean;
  onApplied: (playbook: PlaybookDetail) => void;
  onSourceAccepted?: (sourceYaml: string, report: PlaybookCompatibilityReport) => void;
}

export function PlaybookCompatibilityPanel({
  lang,
  playbookId,
  sourcePath,
  sourceYaml,
  report: initialReport,
  canAdapt = true,
  onApplied,
  onSourceAccepted,
}: PlaybookCompatibilityPanelProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const queryClient = useQueryClient();
  const [report, setReport] = useState<PlaybookCompatibilityReport>(initialReport || {});
  const [busy, setBusy] = useState<"analyze" | "adapt" | "apply" | null>(null);
  const [lastFailure, setLastFailure] = useState("");
  const [instruction, setInstruction] = useState("");
  const [proposalBase, setProposalBase] = useState<PlaybookCompatibilityBase | null>(null);
  const [proposal, setProposal] = useState<
    Awaited<ReturnType<typeof adaptPlaybookCompatibility>>["proposal"] | null
  >(null);

  useEffect(() => setReport(initialReport || {}), [initialReport]);

  useEffect(() => { setProposal(null); setProposalBase(null); }, [canAdapt, playbookId, sourcePath, sourceYaml]);

  useEffect(() => {
    if (!playbookId || !sourceYaml || (initialReport?.analyzer_version || 0) >= 3) return;
    let active = true;
    void analyzePlaybookCompatibility(playbookId, sourcePath ? { path: sourcePath } : {})
      .then((result) => {
        if (active) setReport(result.report || {});
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [initialReport?.analyzer_version, playbookId, sourcePath, sourceYaml]);

  const status = report.status || "needs_adaptation";
  const hasErrors = useMemo(() => (report.issues || []).some((issue) => issue.severity === "error"), [report]);
  const statusMeta =
    status === "ready"
      ? { label: tr("Готов", "Ready"), className: "border-success/30 bg-success/10 text-success" }
      : status === "blocked"
        ? { label: tr("Заблокирован", "Blocked"), className: "border-destructive/40 bg-destructive/10 text-destructive" }
        : status === "needs_binding"
          ? { label: tr("Нужны серверы", "Servers required"), className: "border-warning/30 bg-warning/10 text-warning" }
          : { label: tr("Нужна правка", "Needs fix"), className: "border-warning/30 bg-warning/10 text-warning" };

  if (!sourceYaml) return null;

  const analyze = async () => {
    setBusy("analyze");
    setLastFailure("");
    try {
      const result = playbookId
        ? await analyzePlaybookCompatibility(playbookId, { ...(sourcePath ? { path: sourcePath } : {}), source_yaml: sourceYaml })
        : await analyzePlaybookSource(sourceYaml);
      setReport(result.report || {});
      notify.success({ title: tr("Проверка завершена", "Compatibility checked") });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setLastFailure(message);
      notify.error({ title: tr("Проверка не удалась", "Compatibility check failed"), description: message });
    } finally {
      setBusy(null);
    }
  };

  const prepareAdaptation = async () => {
    setBusy("adapt");
    setLastFailure("");
    try {
      const result = playbookId
        ? await adaptPlaybookCompatibility(playbookId, { ...(sourcePath ? { path: sourcePath } : {}), instruction: instruction.trim() || undefined })
        : await adaptPlaybookSource(sourceYaml, { instruction: instruction.trim() || undefined });
      const nextProposal = result.proposal;
      setReport(nextProposal.report || report);
      if (!nextProposal.semantic_guard?.passed || !nextProposal.adapted_yaml) {
        const reason = (nextProposal.semantic_guard?.violations || []).join("; ") || tr("Предложение не прошло semantic guard.", "The proposal did not pass the semantic guard.");
        setLastFailure(reason);
        notify.error({
          title: tr("ИИ-патч отклонён", "AI patch rejected"),
          description: reason,
        });
        return;
      }
      setProposal(nextProposal);
      setProposalBase(result.base || null);
      notify.success({
        title: tr("Предложение готово к проверке", "Proposal ready for review"),
        description: tr(
          "Изменения ещё не применены. Проверьте YAML и подтвердите отдельно.",
          "Nothing has been applied yet. Review the YAML and confirm separately.",
        ),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setLastFailure(message);
      notify.error({ title: tr("Автоадаптация не удалась", "Automatic adaptation failed"), description: message });
    } finally {
      setBusy(null);
    }
  };

  const applyProposal = async () => {
    if (!proposal?.semantic_guard?.passed || !proposal.adapted_yaml) return;
    setBusy("apply");
    setLastFailure("");
    try {
      if (!playbookId) {
        onSourceAccepted?.(proposal.adapted_yaml, proposal.report || {});
        setReport(proposal.report || {});
      } else {
        if (!proposalBase) throw new Error(tr("Основа предложения устарела. Подготовьте адаптацию снова.", "The proposal base is missing or stale. Prepare the adaptation again."));
        const applied = await applyPlaybookCompatibility(playbookId, {
          path: proposalBase.path,
          adapted_yaml: proposal.adapted_yaml,
          changes: proposal.changes,
          expected_content_hash: proposalBase.content_hash,
          expected_bundle_hash: proposalBase.bundle_hash,
          expected_draft_version: proposalBase.draft_version,
          base_revision_id: proposalBase.base_revision_id,
        });
        if (applied.playbook) onApplied(applied.playbook);
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["playbook-workspace", "draft", playbookId] }),
          queryClient.invalidateQueries({ queryKey: ["playbook-workspace", "files", playbookId] }),
          queryClient.invalidateQueries({ queryKey: ["playbook-workspace", "file", playbookId, proposalBase.path] }),
        ]);
        setReport(applied.revision?.report || applied.report || proposal.report || {});
      }
      setProposal(null);
      notify.success({
        title: playbookId ? tr("Правка принята", "Fix accepted") : tr("Правка добавлена в редактор", "Fix added to the editor"),
        description: tr(
          "Проверьте YAML и при необходимости запустите.",
          "Review the YAML and run when ready.",
        ),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setLastFailure(message);
      notify.error({ title: tr("Не удалось применить предложение", "Failed to apply proposal"), description: message });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4 shadow-elev-1">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">{tr("Проверка YAML", "YAML check")}</h3>
            <span className={cn("rounded-sm border px-2 py-0.5 text-2xs font-medium", statusMeta.className)}>
              {statusMeta.label}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {tr(
              "Проверим YAML. Если нужна правка — увидите diff и нажмёте «Принять».",
              "Check the YAML. If a fix is needed, review the diff and press Accept.",
            )}
          </p>
        </div>
        <Button size="sm" variant="outline" className="h-8 gap-1.5" disabled={busy !== null || Boolean(proposal)} onClick={() => void analyze()}>
          <RefreshCw className={cn("h-3.5 w-3.5", busy === "analyze" && "animate-spin")} />
          {tr("Проверить", "Analyze")}
        </Button>
      </div>

      {(report.issues || []).length > 0 ? (
        <div className="space-y-1.5">
          {(report.issues || []).slice(0, 8).map((issue, index) => (
            <div
              key={`${issue.code}-${issue.path || index}`}
              className={cn(
                "flex items-start gap-2 rounded-sm border px-3 py-2 text-xs",
                issue.severity === "error"
                  ? "border-destructive/30 bg-destructive/5 text-foreground"
                  : "border-warning/20 bg-warning/5 text-muted-foreground",
              )}
            >
              <AlertTriangle className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", issue.severity === "error" ? "text-destructive" : "text-warning")} />
              <span>{issue.message}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className={cn("flex items-center gap-2 text-xs", status === "ready" ? "text-success" : "text-warning")}>
          {status === "ready" ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
          {status === "ready"
            ? tr("Статическая проверка и Ansible syntax-check пройдены: можно выбирать серверы.", "Static checks and Ansible syntax-check passed: you can choose servers.")
            : tr("Блокирующих ошибок нет, но скрипту ещё нужна правка или выбор серверов.", "There are no blocking errors, but the script still needs a fix or server selection.")}
        </div>
      )}

      {lastFailure ? (
        <div className="rounded-sm border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {lastFailure}
        </div>
      ) : null}

      {proposal && canAdapt ? (
        <section className="space-y-3 rounded-sm border border-primary/30 bg-primary/5 p-3" aria-label={tr("Проверка предложения", "Proposal review")}>
          <div>
            <h4 className="text-sm font-semibold text-foreground">{tr("Проверьте изменения перед применением", "Review before applying")}</h4>
            <p className="mt-1 text-xs text-muted-foreground">
              {tr("Ни одно изменение ещё не применено.", "No changes have been applied yet.")}
            </p>
          </div>
          {(proposal.changes || []).length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              {proposal.changes.map((change, index) => <li key={`${change}-${index}`}>{change}</li>)}
            </ul>
          ) : null}
          <details open className="rounded-sm border border-border bg-surface-0">
            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-foreground">
              {tr("Изменения YAML", "YAML changes")}
            </summary>
            <YamlDiff before={sourceYaml} after={proposal.adapted_yaml} />
          </details>
          <div className="flex flex-wrap justify-end gap-2">
            <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => setProposal(null)}>
              {tr("Отклонить", "Discard")}
            </Button>
            <Button size="sm" disabled={busy !== null} onClick={() => void applyProposal()}>
              {busy === "apply" ? tr("Принимаем…", "Accepting…") : tr("Принять", "Accept")}
            </Button>
          </div>
        </section>
      ) : null}

      {canAdapt && status !== "ready" ? (
        <div className="space-y-2 border-t border-border pt-4">
          <Textarea
            value={instruction}
            rows={2}
            onChange={(event) => setInstruction(event.target.value)}
            placeholder={tr("Уточнение для ИИ (необязательно)", "AI instruction (optional)")}
            aria-label={tr("Уточнение для ИИ", "AI instruction")}
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="max-w-2xl text-xs text-muted-foreground">
              {tr(
                hasErrors
                  ? "ИИ подготовит предложение. Diff и YAML нужно принять отдельно."
                  : "ИИ учтёт проверку и покажет diff. Применение — только после «Принять».",
                hasErrors
                  ? "AI prepares a proposal. Review the diff and YAML, then accept."
                  : "AI uses the check report and shows a diff. Nothing applies until you accept.",
              )}
            </p>
            <Button
              size="sm"
              className="h-9 gap-1.5"
              disabled={busy !== null || Boolean(proposal)}
              onClick={() => void prepareAdaptation()}
            >
              <Bot className="h-3.5 w-3.5" />
              {busy === "adapt" ? tr("Готовим…", "Preparing…") : tr("Исправить с ИИ", "Fix with AI")}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function YamlDiff({ before, after }: { before: string; after: string }) {
  const lines = useMemo(() => buildLineDiff(before, after), [after, before]);
  return (
    <div className="max-h-96 overflow-auto border-t border-border bg-terminal-bg font-mono text-xs" role="region" aria-label="YAML diff">
      {lines.map((line, index) => (
        <div key={`${line.kind}-${index}`} className={cn(
          "grid grid-cols-[2rem_minmax(0,1fr)] gap-2 px-3 py-0.5",
          line.kind === "add" && "bg-success/10 text-success",
          line.kind === "remove" && "bg-destructive/10 text-destructive",
          line.kind === "same" && "text-muted-foreground",
        )}>
          <span aria-hidden>{line.kind === "add" ? "+" : line.kind === "remove" ? "−" : " "}</span>
          <span className="whitespace-pre-wrap break-words">{line.text || " "}</span>
        </div>
      ))}
    </div>
  );
}

function buildLineDiff(before: string, after: string): Array<{ kind: "same" | "add" | "remove"; text: string }> {
  const left = before.split("\n");
  const right = after.split("\n");
  let prefix = 0;
  while (prefix < left.length && prefix < right.length && left[prefix] === right[prefix]) prefix += 1;
  let suffix = 0;
  while (suffix < left.length - prefix && suffix < right.length - prefix && left[left.length - 1 - suffix] === right[right.length - 1 - suffix]) suffix += 1;
  return [
    ...left.slice(0, prefix).map((text) => ({ kind: "same" as const, text })),
    ...left.slice(prefix, left.length - suffix).map((text) => ({ kind: "remove" as const, text })),
    ...right.slice(prefix, right.length - suffix).map((text) => ({ kind: "add" as const, text })),
    ...left.slice(left.length - suffix).map((text) => ({ kind: "same" as const, text })),
  ];
}
