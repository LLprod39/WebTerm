import type { Dispatch, SetStateAction } from "react";
import { UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ACCESS_UI_TEXT, getAccessProfileLabel } from "@/lib/accessUiText";
import { toggleId } from "./accessUserPermissions";
import { FieldLabel, GroupPicker, SELECT_CLASS } from "./SettingsUsersShared";
import type { AccessGroupOption, UserCreateForm } from "./settingsUsersTypes";

type AsyncAction = () => void | Promise<void>;

export function CreateUserSidebar({
  lang,
  groups,
  createForm,
  saving,
  onCreateUser,
  onCreateFormChange,
}: {
  lang: "en" | "ru";
  groups: AccessGroupOption[];
  createForm: UserCreateForm;
  saving: boolean;
  onCreateUser: AsyncAction;
  onCreateFormChange: Dispatch<SetStateAction<UserCreateForm>>;
}) {
  const copy = ACCESS_UI_TEXT[lang].users;
  const common = ACCESS_UI_TEXT[lang].common;

  return (
    <div className="order-first h-fit rounded-xl border border-border bg-card shadow-sm xl:order-none xl:sticky xl:top-4">
      <div className="flex items-center gap-3 border-b border-border/60 px-5 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
          <UserPlus className="h-4 w-4" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-foreground">{copy.createTitle}</h2>
          <p className="text-[11px] text-muted-foreground/60">{copy.createHint}</p>
        </div>
      </div>
      <div className="space-y-4 px-5 py-5">
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
          />
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
          />
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
          />
        </div>
        <div>
          <FieldLabel htmlFor="create-user-profile">{common.profile}</FieldLabel>
          <select
            id="create-user-profile"
            value={createForm.access_profile}
            onChange={(event) => onCreateFormChange((state) => ({ ...state, access_profile: event.target.value }))}
            className={SELECT_CLASS}
            aria-label={common.profile}
          >
            <option value="server_only">{getAccessProfileLabel(lang, "server_only")}</option>
            <option value="admin_full">{getAccessProfileLabel(lang, "admin_full")}</option>
            <option value="custom">{getAccessProfileLabel(lang, "custom")}</option>
            <option value="reset_defaults">{getAccessProfileLabel(lang, "reset_defaults")}</option>
          </select>
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
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">{common.groups}</div>
          <GroupPicker
            groups={groups}
            selectedGroupIds={createForm.groups}
            onToggle={(groupId) => onCreateFormChange((state) => ({ ...state, groups: toggleId(state.groups, groupId) }))}
          />
        </div>

        <Button
          className="h-10 w-full"
          onClick={() => void onCreateUser()}
          disabled={saving || !createForm.username.trim() || !createForm.password.trim()}
        >
          {saving ? copy.creatingAction : copy.createAction}
        </Button>
      </div>
    </div>
  );
}
