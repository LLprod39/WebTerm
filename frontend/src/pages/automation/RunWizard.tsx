import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, Loader2, Play } from "lucide-react";

import {
  validatePlaybookRevision,
  type PlaybookRunRequest,
  type PlaybookRunValidation,
} from "@/api/playbook-preflight";
import type {
  PlaybookBindingProfile,
  PlaybookCapabilities,
  PlaybookCompatibilityReport,
  PlaybookRevision,
} from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import type { FrontendGroup, FrontendServer } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ReviewValidationStep } from "./run-preflight/ReviewValidationStep";
import { RevisionRuntimeStep } from "./run-preflight/RevisionRuntimeStep";
import { TargetsBindingStep } from "./run-preflight/TargetsBindingStep";
import { VariablesPolicyStep } from "./run-preflight/VariablesPolicyStep";
import {
  bindingsComplete,
  buildAdhocBindings,
  buildRunRequest,
  buildRunTargetContext,
  buildValidationPayload,
  parseExtraVarsJson,
  pruneAdhocBindingChoices,
  type ExtraVarsParseError,
  type RunPolicyOptions,
} from "./runPreflightState";

type RunWizardStep = 1 | 2;

interface RunWizardProps {
  lang: string;
  playbookName: string;
  servers: FrontendServer[];
  groups: FrontendGroup[];
  running: boolean;
  onBack: () => void;
  onConfirm: (payload: PlaybookRunRequest) => void;
  ansibleAvailable?: boolean;
  workerReady?: boolean;
  playbookId: number;
  compatibility?: PlaybookCompatibilityReport;
  revisions: PlaybookRevision[];
  publishedRevisionId: number | null;
  revisionsLoading: boolean;
  bindingProfiles: PlaybookBindingProfile[];
  capabilities: PlaybookCapabilities;
}

const initialPolicy: RunPolicyOptions = {
  concurrency: 4,
  dryRun: false,
  become: true,
  tags: "",
  skipTags: "",
  limit: "",
};

export function RunWizard({
  lang,
  playbookName,
  servers,
  groups,
  running,
  onBack,
  onConfirm,
  ansibleAvailable = false,
  workerReady = false,
  playbookId,
  compatibility,
  revisions,
  publishedRevisionId,
  revisionsLoading,
  bindingProfiles,
  capabilities,
}: RunWizardProps) {
  const tr = useCallback((ru: string, en: string) => (lang === "ru" ? ru : en), [lang]);
  const validationSequence = useRef(0);
  const profileInitialized = useRef(false);
  const fingerprintRef = useRef("");
  const [step, setStep] = useState<RunWizardStep>(1);
  const [selectedRevisionId, setSelectedRevisionId] = useState<number | null>(null);
  const [selectedBindingProfileId, setSelectedBindingProfileId] = useState<number | null>(null);
  const [serverIds, setServerIds] = useState<Set<number>>(new Set());
  const [groupIds, setGroupIds] = useState<Set<number>>(new Set());
  const [bindingChoices, setBindingChoices] = useState<Record<string, string>>({});
  const [extraVarsText, setExtraVarsText] = useState("{}\n");
  const [extraVars, setExtraVars] = useState<Record<string, unknown>>({});
  const [extraVarsError, setExtraVarsError] = useState<ExtraVarsParseError>(null);
  const [policy, setPolicy] = useState<RunPolicyOptions>(initialPolicy);
  const [validation, setValidation] = useState<PlaybookRunValidation | null>(null);
  const [validating, setValidating] = useState(false);
  const [validationError, setValidationError] = useState("");

  const visibleRevisions = useMemo(
    () => capabilities.can_edit
      ? revisions
      : revisions.filter((revision) => revision.id === publishedRevisionId),
    [capabilities.can_edit, publishedRevisionId, revisions],
  );
  const selectedRevision = visibleRevisions.find((revision) => revision.id === selectedRevisionId) || null;
  const selectedProfile = bindingProfiles.find((profile) => profile.id === selectedBindingProfileId) || null;
  const revisionCompatibility = selectedRevision?.compatibility ?? compatibility;
  const hostSelectors = useMemo(
    () => revisionCompatibility?.host_selectors || [],
    [revisionCompatibility?.host_selectors],
  );
  const requiredVariableNames = useMemo(
    () => revisionCompatibility?.required_variables || [],
    [revisionCompatibility?.required_variables],
  );
  const isRunbook = selectedRevision?.content_format === "runbook_json";
  const runtimeReady = isRunbook ? workerReady : ansibleAvailable && workerReady;
  const onlineIds = useMemo(
    () => new Set(servers.filter((server) => server.status === "online").map((server) => server.id)),
    [servers],
  );
  const inventoryBindings = useMemo(
    () => buildAdhocBindings(hostSelectors, bindingChoices, serverIds, groupIds),
    [bindingChoices, groupIds, hostSelectors, serverIds],
  );
  const targetContext = useMemo(
    () => buildRunTargetContext({
      bindingProfile: selectedProfile,
      serverIds,
      groupIds,
      inventoryBindings,
      extraVars,
    }),
    [extraVars, groupIds, inventoryBindings, selectedProfile, serverIds],
  );
  const targetReady = Boolean(
    (targetContext.serverIds.length || targetContext.groupIds.length) &&
      bindingsComplete(hostSelectors, targetContext.inventoryBindings),
  );
  const canValidateContext = capabilities.can_validate || capabilities.can_run;

  useEffect(() => {
    if (!visibleRevisions.length) {
      setSelectedRevisionId(null);
      return;
    }
    setSelectedRevisionId((current) => {
      if (current && visibleRevisions.some((revision) => revision.id === current)) return current;
      if (publishedRevisionId && visibleRevisions.some((revision) => revision.id === publishedRevisionId)) {
        return publishedRevisionId;
      }
      return visibleRevisions[0].id;
    });
  }, [publishedRevisionId, visibleRevisions]);

  useEffect(() => {
    if (profileInitialized.current || !bindingProfiles.length) return;
    profileInitialized.current = true;
    const defaultProfile = bindingProfiles.find((profile) => profile.is_default);
    if (!defaultProfile) return;
    setSelectedBindingProfileId(defaultProfile.id);
    setPolicy(policyFromProfile(defaultProfile));
  }, [bindingProfiles]);

  useEffect(() => {
    setBindingChoices((current) => pruneAdhocBindingChoices(current, serverIds, groupIds));
  }, [groupIds, serverIds]);

  const contextFingerprint = useMemo(
    () => JSON.stringify({ selectedRevisionId, targetContext, extraVarsText, extraVars, policy }),
    [extraVars, extraVarsText, policy, selectedRevisionId, targetContext],
  );

  useEffect(() => {
    if (!fingerprintRef.current) {
      fingerprintRef.current = contextFingerprint;
      return;
    }
    if (fingerprintRef.current === contextFingerprint) return;
    fingerprintRef.current = contextFingerprint;
    validationSequence.current += 1;
    setValidation(null);
    setValidationError("");
    setValidating(false);
  }, [contextFingerprint]);

  const selectBindingProfile = (profileId: number | null) => {
    setSelectedBindingProfileId(profileId);
    const profile = bindingProfiles.find((item) => item.id === profileId);
    if (profile) setPolicy(policyFromProfile(profile));
  };
  const toggleServer = (serverId: number) => setServerIds((previous) => toggledSet(previous, serverId));
  const toggleGroup = (groupId: number) => setGroupIds((previous) => toggledSet(previous, groupId));
  const updateExtraVars = (source: string) => {
    setExtraVarsText(source);
    const parsed = parseExtraVarsJson(source);
    setExtraVarsError(parsed.error);
    if (parsed.value) setExtraVars(parsed.value);
  };

  const runValidation = useCallback(async () => {
    if (!selectedRevisionId || extraVarsError || !runtimeReady) return null;
    if (!canValidateContext) {
      setValidationError(tr("Нет права проверять или запускать этот playbook.", "You cannot validate or run this playbook."));
      return null;
    }
    const sequence = validationSequence.current + 1;
    validationSequence.current = sequence;
    setValidating(true);
    setValidation(null);
    setValidationError("");
    try {
      const response = await validatePlaybookRevision(
        playbookId,
        selectedRevisionId,
        buildValidationPayload(targetContext),
      );
      if (validationSequence.current !== sequence) return null;
      setValidation(response.validation);
      return response.validation;
    } catch (error) {
      if (validationSequence.current !== sequence) return null;
      setValidationError(error instanceof Error ? error.message : String(error));
      return null;
    } finally {
      if (validationSequence.current === sequence) setValidating(false);
    }
  }, [canValidateContext, extraVarsError, playbookId, runtimeReady, selectedRevisionId, targetContext, tr]);

  const openReview = () => {
    if (extraVarsError || !runtimeReady || !targetReady) return;
    setStep(2);
    void runValidation();
  };

  const confirmRun = () => {
    if (!capabilities.can_run || !selectedRevisionId || validation?.status !== "ready" || !runtimeReady) return;
    onConfirm(buildRunRequest({
      revisionId: selectedRevisionId,
      validationId: validation.id,
      context: targetContext,
      extraVars,
      policy,
    }));
  };

  return (
    <section className="mx-auto w-full max-w-[1180px] space-y-5">
      <header className="flex flex-col gap-4 border-b border-border/70 pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <button type="button" onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground">
            ← {tr("К playbook", "Back to playbook")}
          </button>
          <h1 className="mt-2 font-display text-xl font-semibold tracking-tight text-foreground">
            {tr("Запуск", "Run")}: {playbookName}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {step === 1
              ? tr("Выберите серверы и при необходимости измените параметры.", "Choose targets and adjust optional settings.")
              : tr("Проверьте итог и подтвердите запуск.", "Review the result and confirm the run.")}
          </p>
        </div>
        <ol className="flex items-center gap-2" aria-label={tr("Этапы запуска", "Run steps")}>
          {[tr("Настройка", "Setup"), tr("Проверка", "Review")].map((label, index) => {
            const number = (index + 1) as RunWizardStep;
            const active = step === number;
            const complete = step > number;
            return (
              <li key={label} aria-current={active ? "step" : undefined} className="flex items-center gap-2 text-xs">
                <span className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full border font-medium",
                  active && "border-foreground bg-foreground text-background",
                  complete && "border-success/40 bg-success/10 text-success",
                  !active && !complete && "border-border text-muted-foreground",
                )}>
                  {complete ? <CheckCircle2 className="h-3.5 w-3.5" /> : number}
                </span>
                <span className={active ? "font-medium text-foreground" : "text-muted-foreground"}>{label}</span>
              </li>
            );
          })}
        </ol>
      </header>

      {!runtimeReady ? (
        <div role="alert" className="flex items-start gap-3 border-l-2 border-warning bg-warning/[0.045] px-4 py-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div>
            <p className="text-sm font-medium text-foreground">{tr("Запуск сейчас недоступен", "Execution is currently unavailable")}</p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {!workerReady
                ? tr("Worker выполнения не подключён. Настройки можно подготовить, но WebTerm не будет запускать долгую проверку впустую.", "The execution worker is offline. You can prepare settings, but WebTerm will not run a validation that cannot be executed.")
                : tr("Проверка Ansible runtime недоступна. Проверьте системную настройку runtime.", "Ansible runtime validation is unavailable. Check the system runtime configuration.")}
            </p>
          </div>
        </div>
      ) : null}

      {step === 1 ? (
        <div className="space-y-4">
          <TargetsBindingStep
            lang={lang}
            servers={servers}
            groups={groups}
            bindingProfiles={bindingProfiles}
            selectedBindingProfileId={selectedBindingProfileId}
            selectedServerIds={serverIds}
            selectedGroupIds={groupIds}
            hostSelectors={hostSelectors}
            inventoryBindings={targetContext.inventoryBindings}
            bindingChoices={bindingChoices}
            onBindingProfileChange={selectBindingProfile}
            onToggleServer={toggleServer}
            onToggleGroup={toggleGroup}
            onSelectOnline={() => setServerIds(new Set(onlineIds))}
            onClearTargets={() => { setServerIds(new Set()); setGroupIds(new Set()); }}
            onBindingChoiceChange={(selector, choice) => setBindingChoices((current) => ({ ...current, [selector]: choice }))}
          />

          <details className="group overflow-hidden rounded-lg border border-border/80 bg-card/45" open={requiredVariableNames.length > 0 || Boolean(extraVarsError)}>
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium text-foreground marker:content-none">
              <span>
                {tr("Версия и дополнительные параметры", "Revision and advanced settings")}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  {selectedRevision ? `#${selectedRevision.revision_number}` : "—"} · {policy.dryRun ? "dry-run" : tr("обычный запуск", "normal run")}
                </span>
              </span>
              <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
            </summary>
            <div className="space-y-4 border-t border-border/70 p-4">
              <RevisionRuntimeStep
                lang={lang}
                revisions={visibleRevisions}
                selectedRevisionId={selectedRevisionId}
                publishedRevisionId={publishedRevisionId}
                capabilities={capabilities}
                ansibleAvailable={ansibleAvailable}
                workerReady={workerReady}
                loading={revisionsLoading}
                onRevisionChange={setSelectedRevisionId}
              />
              <VariablesPolicyStep
                lang={lang}
                bindingProfile={selectedProfile}
                extraVarsText={extraVarsText}
                extraVarsError={extraVarsError}
                availableVariableNames={targetContext.variableNames}
                requiredVariableNames={requiredVariableNames}
                policy={policy}
                onExtraVarsChange={updateExtraVars}
                onPolicyChange={(patch) => setPolicy((current) => ({ ...current, ...patch }))}
              />
            </div>
          </details>
        </div>
      ) : (
        <ReviewValidationStep
          lang={lang}
          playbookName={playbookName}
          revision={selectedRevision}
          bindingProfile={selectedProfile}
          context={targetContext}
          extraVars={extraVars}
          policy={policy}
          validation={validation}
          validating={validating}
          validationError={validationError}
          onRetry={() => void runValidation()}
        />
      )}

      <footer className="flex flex-col-reverse gap-3 border-t border-border/70 pt-4 sm:flex-row sm:items-center sm:justify-between">
        <Button
          size="sm"
          variant="ghost"
          className="h-9 sm:px-2"
          disabled={running || validating}
          onClick={() => step === 1 ? onBack() : setStep(1)}
        >
          ← {step === 1 ? tr("Отмена", "Cancel") : tr("Изменить настройки", "Change settings")}
        </Button>

        {step === 1 ? (
          <div className="flex flex-col items-stretch gap-1.5 sm:items-end">
            <Button
              size="sm"
              className="h-9 px-5"
              disabled={!selectedRevisionId || revisionsLoading || !canValidateContext || !targetReady || Boolean(extraVarsError) || !runtimeReady}
              onClick={openReview}
            >
              {tr("Проверить и продолжить", "Validate and continue")}
            </Button>
            {!targetReady ? <span className="text-2xs text-muted-foreground">{tr("Выберите хотя бы одну цель", "Choose at least one target")}</span> : null}
          </div>
        ) : (
          <Button
            size="sm"
            className="h-9 gap-1.5 px-5"
            disabled={running || validating || validation?.status !== "ready" || !runtimeReady || !capabilities.can_run}
            onClick={confirmRun}
          >
            {running || validating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {running
              ? tr("Запускаем…", "Starting…")
              : policy.dryRun
                ? tr("Запустить проверочный прогон", "Start dry run")
                : tr("Запустить", "Run now")}
          </Button>
        )}
      </footer>
    </section>
  );
}

function toggledSet(previous: Set<number>, value: number): Set<number> {
  const next = new Set(previous);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

function policyFromProfile(profile: PlaybookBindingProfile): RunPolicyOptions {
  return {
    concurrency: Math.max(1, Math.min(Number(profile.options.concurrency) || 4, 12)),
    dryRun: Boolean(profile.options.dry_run),
    become: profile.options.become ?? true,
    tags: profile.options.tags || "",
    skipTags: profile.options.skip_tags || "",
    limit: profile.options.limit || "",
  };
}
