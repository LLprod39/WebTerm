import type { Dispatch, SetStateAction } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { InlineAlert } from "@/components/system/InlineAlert";
import { ACCESS_UI_TEXT, getAccessProfileLabel } from "@/lib/accessUiText";
import { toggleId } from "./accessUserPermissions";
import { FieldLabel, GroupPicker, SELECT_CLASS } from "./SettingsUsersShared";
import type { AccessGroupOption, UserCreateForm } from "./settingsUsersTypes";
import type { UserValidationResult } from "./userValidation";

type AsyncAction = () => boolean | Promise<boolean>;

export function CreateUserSidebar({
  lang,
  groups,
  createForm,
  validation,
  saving,
  onCreateUser,
  onCreateFormChange,
}: {
  lang: "en" | "ru";
  groups: AccessGroupOption[];
  createForm: UserCreateForm;
  validation: UserValidationResult;
  saving: boolean;
  onCreateUser: AsyncAction;
  onCreateFormChange: Dispatch<SetStateAction<UserCreateForm>>;
}) {
  const copy = ACCESS_UI_TEXT[lang].users;
  const common = ACCESS_UI_TEXT[lang].common;
  const showFieldErrors = Boolean(createForm.username || createForm.email || createForm.password);

  return (
    <div className="space-y-5 px-6 py-5">
      <div className="space-y-4">
        <div>
          <FieldLabel htmlFor="create-user-username">{copy.username}</FieldLabel>
          <Input
            id="create-user-username"
            name="username"
            autoComplete="username"
            spellCheck={false}
            placeholder={copy.username}
            value={createForm.username}
            onChange={(event) => onCreateFormChange((state) => ({ ...state, username: event.target.value }))}
            className="h-10 bg-secondary/20 border-border/60"
            aria-invalid={Boolean(showFieldErrors && validation.errors.username)}
            aria-describedby={showFieldErrors && validation.errors.username ? "create-user-username-error" : undefined}
          />
          {showFieldErrors && validation.errors.username ? (
            <p id="create-user-username-error" className="mt-1 text-xs text-destructive">{validation.errors.username}</p>
          ) : null}
        </div>
        <div>
          <FieldLabel htmlFor="create-user-email">{copy.email}</FieldLabel>
          <Input
            id="create-user-email"
            name="email"
            type="email"
            autoComplete="email"
            spellCheck={false}
            placeholder={copy.email}
            value={createForm.email}
            onChange={(event) => onCreateFormChange((state) => ({ ...state, email: event.target.value }))}
            className="h-10 bg-secondary/20 border-border/60"
            aria-invalid={Boolean(showFieldErrors && validation.errors.email)}
            aria-describedby={showFieldErrors && validation.errors.email ? "create-user-email-error" : undefined}
          />
          {showFieldErrors && validation.errors.email ? (
            <p id="create-user-email-error" className="mt-1 text-xs text-destructive">{validation.errors.email}</p>
          ) : null}
        </div>
        <div>
          <FieldLabel htmlFor="create-user-password">{common.password}</FieldLabel>
          <Input
            id="create-user-password"
            name="new-password"
            type="password"
            autoComplete="new-password"
            placeholder={copy.passwordPlaceholder}
            value={createForm.password}
            onChange={(event) => onCreateFormChange((state) => ({ ...state, password: event.target.value }))}
            className="h-10 bg-secondary/20 border-border/60"
            aria-invalid={Boolean(showFieldErrors && validation.errors.password)}
            aria-describedby={showFieldErrors && validation.errors.password ? "create-user-password-error" : undefined}
          />
          {showFieldErrors && validation.errors.password ? (
            <p id="create-user-password-error" className="mt-1 text-xs text-destructive">{validation.errors.password}</p>
          ) : null}
        </div>
        <div>
          <FieldLabel htmlFor="create-user-profile">{common.profile}</FieldLabel>
          <Select
            value={createForm.access_profile}
            onValueChange={(value) => onCreateFormChange((state) => ({ ...state, access_profile: value }))}
          >
            <SelectTrigger id="create-user-profile" className={SELECT_CLASS} aria-label={common.profile}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="server_only">{getAccessProfileLabel(lang, "server_only")}</SelectItem>
              <SelectItem value="admin_full">{getAccessProfileLabel(lang, "admin_full")}</SelectItem>
              <SelectItem value="custom">{getAccessProfileLabel(lang, "custom")}</SelectItem>
              <SelectItem value="reset_defaults">{getAccessProfileLabel(lang, "reset_defaults")}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-wrap gap-5 rounded-lg border border-border/40 bg-secondary/10 px-4 py-3">
          <label className="flex cursor-pointer select-none items-center gap-2.5 text-sm text-foreground/80">
            <Switch checked={createForm.is_staff} onCheckedChange={(value) => onCreateFormChange((state) => ({ ...state, is_staff: value }))} />
            {common.staff}
          </label>
          <label className="flex cursor-pointer select-none items-center gap-2.5 text-sm text-foreground/80">
            <Switch checked={createForm.is_active} onCheckedChange={(value) => onCreateFormChange((state) => ({ ...state, is_active: value }))} />
            {common.active}
          </label>
        </div>

        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{common.groups}</div>
          <GroupPicker
            groups={groups}
            selectedGroupIds={createForm.groups}
            onToggle={(groupId) => onCreateFormChange((state) => ({ ...state, groups: toggleId(state.groups, groupId) }))}
          />
        </div>

        {!validation.isValid ? <InlineAlert tone="warning" description={validation.summary} /> : null}
        <Button
          className="h-10 w-full"
          onClick={() => void onCreateUser()}
          disabled={saving || !validation.isValid}
        >
          {saving ? copy.creatingAction : copy.createAction}
        </Button>
      </div>
    </div>
  );
}
