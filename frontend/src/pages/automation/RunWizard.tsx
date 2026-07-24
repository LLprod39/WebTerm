import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Play } from "lucide-react";

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

type RunWizardStep = 1 | 2 | 3 | 4;

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
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
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
  const runtimeReady = selectedRevision?.content_format === "runbook_json" ? workerReady : ansibleAvailable;
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
    () => JSON.stringify({
      selectedRevisionId,
      targetContext,
      extraVarsText,
      extraVars,
      policy,
    }),
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
    if (!selectedRevisionId || extraVarsError) return null;
    if (!canValidateContext) {
      setValidationError(
        lang === "ru"
          ? "Нет права проверять или запускать этот playbook."
          : "You do not have permission to validate or run this playbook.",
      );
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
  }, [canValidateContext, extraVarsError, lang, playbookId, selectedRevisionId, targetContext]);

  const openReview = () => {
    if (extraVarsError) return;
    setStep(4);
    void runValidation();
  };

  const confirmRun = () => {
    if (!capabilities.can_run || !selectedRevisionId || validation?.status !== "ready") return;
    onConfirm(buildRunRequest({
      revisionId: selectedRevisionId,
      validationId: validation.id,
      context: targetContext,
      extraVars,
      policy,
    }));
  };

  const stepLabels = [
    tr("Ревизия", "Revision"),
    tr("Цели", "Targets"),
    tr("Переменные", "Variables"),
    "Review",
  ];

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <button type="button" onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground">
            ← {tr("Назад", "Back")}
          </button>
          <h2 className="mt-1 font-display text-lg font-semibold text-foreground">
            {tr("Run preflight", "Run preflight")}: {playbookName}
          </h2>
        </div>
        <ol className="flex flex-wrap items-center gap-1.5" aria-label={tr("Шаги preflight", "Preflight steps")}>
          {stepLabels.map((label, index) => {
            const number = (index + 1) as RunWizardStep;
            return (
              <li
                key={label}
                aria-current={step === number ? "step" : undefined}
                className={cn(
                  "flex h-8 items-center justify-center rounded-sm border px-2.5 text-2xs font-medium",
                  step === number
                    ? "border-primary bg-primary text-primary-foreground"
                    : step > number
                      ? "border-primary/40 bg-primary/10 text-primary"
                      : "border-border bg-card text-muted-foreground",
                )}
              >
                {number}. {label}
              </li>
            );
          })}
        </ol>
      </div>

      {step === 1 ? (
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
      ) : null}

      {step === 2 ? (
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
      ) : null}

      {step === 3 ? (
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
      ) : null}

      {step === 4 ? (
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
      ) : null}

      <div className="flex items-center justify-between gap-2">
        <Button
          size="sm"
          variant="outline"
          className="h-9"
          disabled={step === 1 || running || validating}
          onClick={() => setStep((current) => (current > 1 ? (current - 1) as RunWizardStep : current))}
        >
          {tr("Назад", "Back")}
        </Button>

        {step < 4 ? (
          <Button
            size="sm"
            className="h-9 shadow-elev-1"
            disabled={
              (step === 1 && (!selectedRevisionId || revisionsLoading || !canValidateContext)) ||
              (step === 2 && !targetReady) ||
              (step === 3 && Boolean(extraVarsError))
            }
            onClick={() => {
              if (step === 3) openReview();
              else setStep((current) => (current + 1) as RunWizardStep);
            }}
          >
            {step === 3 ? tr("Review и validation", "Review & validate") : tr("Далее", "Next")}
          </Button>
        ) : (
          <Button
            size="sm"
            className="h-9 gap-1.5 px-5 shadow-elev-1"
            disabled={
              running ||
              validating ||
              validation?.status !== "ready" ||
              !runtimeReady ||
              !capabilities.can_run
            }
            onClick={confirmRun}
          >
            {running || validating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {running
              ? tr("Запуск…", "Starting…")
              : policy.dryRun
                ? tr("Запустить dry-run", "Start dry-run")
                : tr("Запустить validated revision", "Run validated revision")}
          </Button>
        )}
      </div>
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
