import { Loader2, Sparkles, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SettingsField, SettingsSectionActions } from "@/components/settings/SettingsPageShell";
import { useI18n } from "@/lib/i18n";
import { AUX_LLM_PROVIDERS } from "./constants";
import { SectionCard } from "./SectionCard";

type AuxModelSettingsProps = {
  disabled: boolean;
  enabled: boolean;
  provider: string;
  model: string;
  baseUrl: string;
  timeoutSeconds: number;
  roleVerifier: boolean;
  roleIntent: boolean;
  roleSummarizer: boolean;
  roleSafety: boolean;
  apiKeyDraft: string;
  apiKeySet: boolean;
  saving: boolean;
  testing: boolean;
  testMessage: string | null;
  onEnabledChange: (value: boolean) => void;
  onProviderChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onBaseUrlChange: (value: string) => void;
  onTimeoutChange: (value: number) => void;
  onRoleVerifierChange: (value: boolean) => void;
  onRoleIntentChange: (value: boolean) => void;
  onRoleSummarizerChange: (value: boolean) => void;
  onRoleSafetyChange: (value: boolean) => void;
  onApiKeyDraftChange: (value: string) => void;
  onSave: () => void;
  onTest: () => void;
};

function RoleToggle({
  label,
  description,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  disabled: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-sm border border-border bg-surface-0/40 px-3 py-2.5">
      <input
        type="checkbox"
        className="mt-1"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        <span className="block text-sm font-medium text-foreground">{label}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground">{description}</span>
      </span>
    </label>
  );
}

export function AuxModelSettings(props: AuxModelSettingsProps) {
  const { t } = useI18n();
  const needsBaseUrl = props.provider === "ollama" || props.provider === "openai_compatible";

  return (
    <SectionCard
      title={t("ai.aux_title")}
      icon={Sparkles}
      description={t("ai.aux_desc")}
      actions={
        props.enabled ? (
          <Badge variant="secondary" className="gap-1">
            <Zap className="h-3 w-3" />
            {t("ai.aux_badge")}
          </Badge>
        ) : undefined
      }
    >
      <div className="space-y-5">
        <label className="flex items-center gap-3 text-sm text-foreground">
          <input
            type="checkbox"
            checked={props.enabled}
            disabled={props.disabled}
            onChange={(event) => props.onEnabledChange(event.target.checked)}
          />
          {t("ai.aux_enable")}
        </label>
        <p className="text-xs text-muted-foreground">{t("ai.aux_help")}</p>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <SettingsField label={t("ai.provider_label")}>
            <Select
              value={props.provider || "ollama"}
              onValueChange={props.onProviderChange}
              disabled={props.disabled || !props.enabled}
            >
              <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                {AUX_LLM_PROVIDERS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </SettingsField>
          <SettingsField label={t("ai.model_label")} hint={t("ai.aux_model_hint")}>
            <Input
              value={props.model}
              onChange={(event) => props.onModelChange(event.target.value)}
              disabled={props.disabled || !props.enabled}
              placeholder="llama3.2 / gpt-4o-mini / …"
              className="h-9 text-sm"
            />
          </SettingsField>
        </div>

        {needsBaseUrl ? (
          <SettingsField label={t("ai.aux_base_url")} hint={t("ai.aux_base_url_hint")}>
            <Input
              value={props.baseUrl}
              onChange={(event) => props.onBaseUrlChange(event.target.value)}
              disabled={props.disabled || !props.enabled}
              placeholder={
                props.provider === "ollama"
                  ? "http://127.0.0.1:11434"
                  : "http://127.0.0.1:1234"
              }
              className="h-9 text-sm font-mono"
            />
          </SettingsField>
        ) : null}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <SettingsField label={t("ai.aux_timeout")} hint={t("ai.aux_timeout_hint")}>
            <Input
              type="number"
              min={2}
              max={30}
              value={props.timeoutSeconds}
              onChange={(event) => props.onTimeoutChange(Number(event.target.value) || 8)}
              disabled={props.disabled || !props.enabled}
              className="h-9 text-sm"
            />
          </SettingsField>
          <SettingsField
            label={t("ai.aux_api_key")}
            hint={props.apiKeySet ? t("ai.connected") : t("ai.not_set")}
          >
            <Input
              type="password"
              value={props.apiKeyDraft}
              onChange={(event) => props.onApiKeyDraftChange(event.target.value)}
              disabled={props.disabled || !props.enabled}
              placeholder={props.apiKeySet ? "••••••••" : t("ai.aux_api_key_placeholder")}
              className="h-9 text-sm"
              autoComplete="off"
            />
          </SettingsField>
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium text-foreground">{t("ai.aux_roles_title")}</p>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            <RoleToggle
              label={t("ai.aux_role_verifier")}
              description={t("ai.aux_role_verifier_desc")}
              checked={props.roleVerifier}
              disabled={props.disabled || !props.enabled}
              onChange={props.onRoleVerifierChange}
            />
            <RoleToggle
              label={t("ai.aux_role_intent")}
              description={t("ai.aux_role_intent_desc")}
              checked={props.roleIntent}
              disabled={props.disabled || !props.enabled}
              onChange={props.onRoleIntentChange}
            />
            <RoleToggle
              label={t("ai.aux_role_summarizer")}
              description={t("ai.aux_role_summarizer_desc")}
              checked={props.roleSummarizer}
              disabled={props.disabled || !props.enabled}
              onChange={props.onRoleSummarizerChange}
            />
            <RoleToggle
              label={t("ai.aux_role_safety")}
              description={t("ai.aux_role_safety_desc")}
              checked={props.roleSafety}
              disabled={props.disabled || !props.enabled}
              onChange={props.onRoleSafetyChange}
            />
          </div>
        </div>

        {!props.disabled ? (
          <SettingsSectionActions>
            <Button
              size="sm"
              variant="secondary"
              className="gap-1.5"
              onClick={props.onTest}
              disabled={!props.enabled || props.testing || props.saving}
            >
              {props.testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
              {t("ai.aux_test")}
            </Button>
            <Button size="sm" className="gap-1.5" onClick={props.onSave} disabled={props.saving}>
              {props.saving ? t("ai.saving") : t("ai.aux_save")}
            </Button>
            {props.testMessage ? (
              <span className="text-xs text-muted-foreground">{props.testMessage}</span>
            ) : null}
          </SettingsSectionActions>
        ) : null}
      </div>
    </SectionCard>
  );
}
