import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { StudioSharedUser } from "@/lib/api";

export function ShareAccessEditor({
  title = "Access",
  description = "Admin can expose this item to everyone with the section enabled or share it with specific users.",
  isShared,
  sharedUserIds,
  users,
  disabled = false,
  onSharedChange,
  onToggleUser,
}: {
  title?: string;
  description?: string;
  isShared: boolean;
  sharedUserIds: number[];
  users: StudioSharedUser[];
  disabled?: boolean;
  onSharedChange: (value: boolean) => void;
  onToggleUser: (userId: number) => void;
}) {
  const availableUsers = Array.isArray(users) ? users : [];

  return (
    <div className="space-y-4 rounded-2xl border border-border/70 bg-background/40 p-4">
      <div className="space-y-1">
        <div className="text-sm font-medium text-foreground">{title}</div>
        <p className="text-xs leading-5 text-muted-foreground">{description}</p>
      </div>

      <div className="flex items-center justify-between gap-3 rounded-xl border border-border/70 bg-background/60 px-3 py-3">
        <div>
          <div className="text-sm font-medium text-foreground">Shared for all users</div>
          <div className="text-xs text-muted-foreground">Everyone with this Studio section can open and use it.</div>
        </div>
        <Switch checked={isShared} onCheckedChange={onSharedChange} disabled={disabled} />
      </div>

      <div className="space-y-2">
        <Label className="text-xs">Share with specific users</Label>
        {availableUsers.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border/70 px-3 py-4 text-xs text-muted-foreground">
            No active users available.
          </div>
        ) : (
          <div className="grid gap-2 md:grid-cols-2">
            {availableUsers.map((user) => {
              const checked = sharedUserIds.includes(user.id);
              return (
                <label
                  key={user.id}
                  className="flex cursor-pointer items-start gap-3 rounded-xl border border-border/70 bg-background/60 px-3 py-3 transition-colors hover:bg-background/80"
                >
                  <Checkbox
                    checked={checked}
                    onCheckedChange={() => onToggleUser(user.id)}
                    disabled={disabled}
                    className="mt-0.5"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-foreground">{user.username}</div>
                    <div className="truncate text-xs text-muted-foreground">{user.email || "No email"}</div>
                  </div>
                  {checked ? <Badge variant="secondary">Shared</Badge> : null}
                </label>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
