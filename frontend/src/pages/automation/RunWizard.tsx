import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Play, Settings2 } from "lucide-react";

import {
  validatePlaybookRevision,
  type PlaybookRunRequest,
  type PlaybookRunValidation,
} from "@/api/playbook-preflight";
import type {
  PlaybookCapabilities,
  PlaybookBindingProfile,
  PlaybookCompatibilityReport,
  PlaybookRevision,
  PlaybookRunRetryContext,
} from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { FrontendGroup, FrontendServer } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ReviewValidationStep } from "./run-preflight/ReviewValidationStep";
import { RunEssentialsStep } from "./run-preflight/RunEssentialsStep";
import { TargetsBindingStep } from "./run-preflight/TargetsBindingStep";
import {
  bindingsComplete,
  buildAdhocBindings,
  buildRunRequest,
  buildRunTargetContext,
  buildValidationPayload,
  pruneAdhocBindingChoices,
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
  bindingProfiles?: PlaybookBindingProfile[];
  bindingsLoading?: boolean;
  capabilities: PlaybookCapabilities;
  retryContext?: PlaybookRunRetryContext | null;
}

const initialPolicy: RunPolicyOptions = {
  concurrency: 4,
  dryRun: true,
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
  bindingProfiles = [],
  bindingsLoading = false,
  capabilities,
  retryContext = null,
}: RunWizardProps) {
  const tr = useCallback((ru: string, en: string) => (lang === "ru" ? ru : en), [lang]);
  const validationSequence = useRef(0);
  const fingerprintRef = useRef("");
  const [step, setStep] = useState<RunWizardStep>(1);
  const [selectedRevisionId, setSelectedRevisionId] = useState<number | null>(null);
  const [selectedBindingProfileId, setSelectedBindingProfileId] = useState<number | null>(null);
  const [serverIds, setServerIds] = useState<Set<number>>(new Set());
  const [groupIds, setGroupIds] = useState<Set<number>>(new Set());
  const [bindingChoices, setBindingChoices] = useState<Record<string, string>>({});
  const [extraVars, setExtraVars] = useState<Record<string, unknown>>({});
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
    () => retryContext?.required_variable_names || revisionCompatibility?.required_variables || [],
    [retryContext?.required_variable_names, revisionCompatibility?.required_variables],
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
  const targetContext = useMemo(() => {
    const context = buildRunTargetContext({
      bindingProfile: selectedProfile,
      serverIds,
      groupIds,
      inventoryBindings,
      extraVars,
    });
    if (!retryContext) return context;
    const failedServerIds = Array.from(new Set(retryContext.failed_server_ids));
    return {
      ...context,
      bindingProfileId: retryContext.binding_profile_id,
      serverIds: failedServerIds,
      groupIds: [],
      inventoryBindings: Object.fromEntries(hostSelectors.map((selector) => [selector, { server_ids: failedServerIds, group_ids: [] }])),
      variableNames: Array.from(new Set([...retryContext.required_variable_names, ...Object.keys(extraVars)])).sort(),
    };
  }, [extraVars, groupIds, hostSelectors, inventoryBindings, retryContext, selectedProfile, serverIds]);
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
      if (retryContext?.revision_id && visibleRevisions.some((revision) => revision.id === retryContext.revision_id)) return retryContext.revision_id;
      if (current && visibleRevisions.some((revision) => revision.id === current)) return current;
      if (publishedRevisionId && visibleRevisions.some((revision) => revision.id === publishedRevisionId)) {
        return publishedRevisionId;
      }
      return visibleRevisions[0].id;
    });
  }, [publishedRevisionId, retryContext?.revision_id, visibleRevisions]);

  useEffect(() => {
    setSelectedBindingProfileId((current) => {
      if (retryContext?.binding_profile_id && bindingProfiles.some((profile) => profile.id === retryContext.binding_profile_id)) return retryContext.binding_profile_id;
      if (current && bindingProfiles.some((profile) => profile.id === current)) return current;
      return bindingProfiles.find((profile) => profile.is_default)?.id || null;
    });
  }, [bindingProfiles, retryContext?.binding_profile_id]);

  useEffect(() => {
    if (!retryContext) return;
    setServerIds(new Set(retryContext.failed_server_ids));
    setGroupIds(new Set());
    const options = retryContext.options;
    setPolicy({
      concurrency: typeof options.concurrency === "number" ? options.concurrency : initialPolicy.concurrency,
      dryRun: typeof options.dry_run === "boolean" ? options.dry_run : true,
      become: typeof options.become === "boolean" ? options.become : initialPolicy.become,
      tags: typeof options.tags === "string" ? options.tags : "",
      skipTags: typeof options.skip_tags === "string" ? options.skip_tags : "",
      limit: typeof options.limit === "string" ? options.limit : "",
    });
  }, [retryContext]);

  useEffect(() => {
    setBindingChoices((current) => pruneAdhocBindingChoices(current, serverIds, groupIds));
  }, [groupIds, serverIds]);

  const contextFingerprint = useMemo(
    () => JSON.stringify({ selectedRevisionId, targetContext, extraVars, policy }),
    [extraVars, policy, selectedRevisionId, targetContext],
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

  const toggleServer = (serverId: number) => setServerIds((previous) => toggledSet(previous, serverId));
  const toggleGroup = (groupId: number) => setGroupIds((previous) => toggledSet(previous, groupId));
  const updateRequiredVariable = (name: string, value: string) => {
    const next = { ...extraVars };
    if (value) next[name] = value;
    else delete next[name];
    setExtraVars(next);
  };
  const profileVariableNames = useMemo(() => new Set<string>(selectedProfile
    ? [...Object.keys(selectedProfile.variable_values || {}), ...(selectedProfile.secret_variables || [])]
    : []), [selectedProfile]);
  const suppliedProfileVariableNames = retryContext?.values_redacted ? new Set<string>() : profileVariableNames;
  const missingRequiredVariableNames = requiredVariableNames.filter(
    (name) => !suppliedProfileVariableNames.has(name) && !Object.prototype.hasOwnProperty.call(extraVars, name),
  );

  const runValidation = useCallback(async () => {
    if (!selectedRevisionId || !runtimeReady) return null;
    if (!canValidateContext) {
      setValidationError(tr("Нет права проверять или запускать этот проект.", "You cannot validate or run this project."));
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
  }, [canValidateContext, playbookId, runtimeReady, selectedRevisionId, targetContext, tr]);

  const openReview = () => {
    if (!runtimeReady || !targetReady) return;
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
      rerunOf: retryContext?.run_id,
    }));
  };

  return (
    <section className="mx-auto w-full max-w-[1180px] space-y-5">
      <header className="flex flex-col gap-4 border-b border-border/70 pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <button type="button" onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground">
            ← {tr("К проекту", "Back to project")}
          </button>
          <h1 className="mt-2 font-display text-xl font-semibold tracking-tight text-foreground">
            {retryContext ? tr("Безопасный повтор", "Safe retry") : tr("Запуск", "Run")}: {playbookName}
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
                ? tr("Сервис запуска недоступен. Настройки можно подготовить сейчас, а запуск выполнить после восстановления сервиса.", "The execution service is unavailable. You can prepare the settings now and run the project after the service is restored.")
                : tr("Проверка Ansible недоступна. Проверьте системные настройки Ansible.", "Ansible validation is unavailable. Check the Ansible system settings.")}
            </p>
          </div>
        </div>
      ) : null}

      {step === 1 ? (
        <div className="space-y-4">
          <section className="rounded-lg border border-border bg-card p-4 shadow-elev-1">
            <div className="grid gap-3 sm:grid-cols-[minmax(0,24rem)_minmax(0,1fr)] sm:items-end">
              <div className="space-y-1.5">
                <Label htmlFor="run-revision">{tr("Версия", "Revision")}</Label>
                <Select value={selectedRevisionId ? String(selectedRevisionId) : ""} onValueChange={(value) => setSelectedRevisionId(Number(value))} disabled={revisionsLoading || Boolean(retryContext)}>
                  <SelectTrigger id="run-revision" aria-label={tr("Версия", "Revision")}><SelectValue placeholder={tr("Выберите опубликованную версию", "Choose a published revision")} /></SelectTrigger>
                  <SelectContent>
                    {visibleRevisions.map((revision) => (
                      <SelectItem key={revision.id} value={String(revision.id)}>
                        #{revision.revision_number}{revision.id === publishedRevisionId ? ` · ${tr("опубликована", "published")}` : ""}{revision.message ? ` · ${revision.message}` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <p className="text-xs leading-5 text-muted-foreground">
                {selectedRevision?.id === publishedRevisionId
                  ? tr("По умолчанию используется опубликованная неизменяемая версия.", "The published immutable revision is selected by default.")
                  : tr("Выбрана неопубликованная версия. Она доступна только редакторам проекта.", "An unpublished revision is selected. It is available only to project editors.")}
              </p>
            </div>
          </section>
          {retryContext ? (
            <section className="rounded-lg border border-primary/30 bg-primary/5 p-4 shadow-elev-1">
              <div className="flex items-start gap-3">
                <CheckCircle2 className="mt-0.5 h-4 w-4 text-primary" />
                <div>
                  <h2 className="text-sm font-semibold text-foreground">{tr("Цели повтора зафиксированы", "Retry targets are locked")}</h2>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    {tr(`Повторно будут проверены ${retryContext.failed_server_ids.length} проблемных серверов из запуска #${retryContext.run_id}. Версия и профиль нельзя подменить.`, `${retryContext.failed_server_ids.length} failed servers from run #${retryContext.run_id} will be validated again. The revision and profile are locked.`)}
                  </p>
                  {retryContext.managed_variable_names.length ? <p className="mt-2 text-xs text-muted-foreground">{tr("Управляемые секреты будут повторно разрешены сервером:", "Managed secrets will be resolved by the server again:")} <span className="font-mono">{retryContext.managed_variable_names.join(", ")}</span></p> : null}
                </div>
              </div>
            </section>
          ) : <TargetsBindingStep
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
            onBindingProfileChange={(profileId) => {
              setSelectedBindingProfileId(profileId);
              const profile = bindingProfiles.find((item) => item.id === profileId);
              if (profile) {
                setPolicy((current) => ({
                  ...current,
                  concurrency: profile.options.concurrency || current.concurrency,
                  become: profile.options.become ?? current.become,
                  dryRun: profile.options.dry_run ?? current.dryRun,
                  tags: profile.options.tags || "",
                  skipTags: profile.options.skip_tags || "",
                  limit: profile.options.limit || "",
                }));
              }
            }}
            onToggleServer={toggleServer}
            onToggleGroup={toggleGroup}
            onSelectOnline={() => setServerIds(new Set(onlineIds))}
            onClearTargets={() => { setServerIds(new Set()); setGroupIds(new Set()); }}
            onBindingChoiceChange={(selector, choice) => setBindingChoices((current) => ({ ...current, [selector]: choice }))}
            showSourceSelector={!bindingsLoading}
          />}

          <RunEssentialsStep
            lang={lang}
            requiredVariableNames={requiredVariableNames}
            profileVariableNames={suppliedProfileVariableNames}
            selectedProfile={selectedProfile}
            extraVars={extraVars}
            dryRun={policy.dryRun}
            onRequiredVariableChange={updateRequiredVariable}
            onDryRunChange={(dryRun) => setPolicy((current) => ({ ...current, dryRun }))}
          />

          <details className="rounded-lg border border-border bg-card shadow-elev-1">
            <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-sm font-medium text-foreground">
              <Settings2 className="h-4 w-4 text-primary" />{tr("Дополнительные настройки", "Advanced settings")}
            </summary>
            <div className="grid gap-4 border-t border-border p-4 md:grid-cols-2 xl:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="run-concurrency">{tr("Параллельность", "Concurrency")}</Label>
                <Input id="run-concurrency" type="number" min={1} max={12} value={policy.concurrency} onChange={(event) => setPolicy((current) => ({ ...current, concurrency: Math.max(1, Math.min(12, Number(event.target.value) || 1)) }))} />
              </div>
              <div className="space-y-2"><Label htmlFor="run-tags">{tr("Теги", "Tags")}</Label><Input id="run-tags" value={policy.tags} onChange={(event) => setPolicy((current) => ({ ...current, tags: event.target.value }))} placeholder="deploy,config" /></div>
              <div className="space-y-2"><Label htmlFor="run-skip-tags">{tr("Пропустить теги", "Skip tags")}</Label><Input id="run-skip-tags" value={policy.skipTags} onChange={(event) => setPolicy((current) => ({ ...current, skipTags: event.target.value }))} placeholder="dangerous" /></div>
              <div className="space-y-2 md:col-span-2"><Label htmlFor="run-limit">{tr("Ограничить узлы", "Limit hosts")}</Label><Input id="run-limit" value={policy.limit} onChange={(event) => setPolicy((current) => ({ ...current, limit: event.target.value }))} placeholder="web:&online" /></div>
              <label className="flex items-center gap-2 self-end pb-2 text-sm text-muted-foreground"><Checkbox checked={policy.become} onCheckedChange={(checked) => setPolicy((current) => ({ ...current, become: checked === true }))} />{tr("Повышенные права (sudo)", "Elevated access (sudo)")}</label>
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
              disabled={!selectedRevisionId || revisionsLoading || !canValidateContext || !targetReady || missingRequiredVariableNames.length > 0 || !runtimeReady}
              onClick={openReview}
            >
              {tr("Проверить и продолжить", "Validate and continue")}
            </Button>
            {!targetReady ? <span className="text-2xs text-muted-foreground">{tr("Выберите хотя бы одну цель", "Choose at least one target")}</span> : null}
            {targetReady && missingRequiredVariableNames.length ? <span className="text-2xs text-muted-foreground">{tr("Заполните обязательные параметры", "Fill in the required parameters")}</span> : null}
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
