import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteAccessPermission,
  fetchAccessPermissions,
  fetchAccessUsers,
  updateAccessPermission,
  upsertAccessPermission,
} from "@/lib/api";
import { Button } from "@/components/ui/button";

function SummaryPill({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-full border border-transparent bg-background/30 px-3 py-1 text-xs text-muted-foreground">
      <span className="font-medium text-foreground">{value}</span> {label}
    </div>
  );
}

export default function SettingsPermissionsPage() {
  const queryClient = useQueryClient();
  const [newUserId, setNewUserId] = useState<number>(0);
  const [newFeature, setNewFeature] = useState<string>("");
  const [newAllowed, setNewAllowed] = useState<boolean>(true);

  const { data: permsData, isLoading, error } = useQuery({
    queryKey: ["access", "permissions"],
    queryFn: fetchAccessPermissions,
  });
  const { data: usersData } = useQuery({ queryKey: ["access", "users"], queryFn: fetchAccessUsers });

  const permissions = useMemo(() => permsData?.permissions ?? [], [permsData?.permissions]);
  const features = useMemo(() => permsData?.features ?? [], [permsData?.features]);
  const users = useMemo(() => usersData?.users ?? [], [usersData?.users]);

  useEffect(() => {
    if (!newUserId && users.length) setNewUserId(users[0].id);
    if (!newFeature && features.length) setNewFeature(features[0].value);
  }, [newUserId, newFeature, users, features]);

  const reload = async () => {
    await queryClient.invalidateQueries({ queryKey: ["access", "permissions"] });
  };

  const onCreate = async () => {
    if (!newUserId || !newFeature) return;
    await upsertAccessPermission({ user_id: newUserId, feature: newFeature, allowed: newAllowed });
    await reload();
  };

  const toggleAllowed = async (permId: number, allowed: boolean) => {
    await updateAccessPermission(permId, !allowed);
    await reload();
  };

  const remove = async (permId: number) => {
    if (!confirm("Delete permission?")) return;
    await deleteAccessPermission(permId);
    await reload();
  };

  if (isLoading) return <div className="p-6 text-sm text-muted-foreground">Loading permissions...</div>;
  if (error) return <div className="p-6 text-sm text-destructive">Failed to load permissions.</div>;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold text-foreground">Permissions</h1>

      <section className="bg-card border border-border rounded-lg p-4 space-y-3">
        <h2 className="text-sm font-medium">Add / Update Permission</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <select
            value={newUserId}
            onChange={(e) => setNewUserId(Number(e.target.value))}
            className="bg-secondary border border-border rounded-md px-3 py-2 text-sm"
          >
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.username}
              </option>
            ))}
          </select>
          <select
            value={newFeature}
            onChange={(e) => setNewFeature(e.target.value)}
            className="bg-secondary border border-border rounded-md px-3 py-2 text-sm"
          >
            {features.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <select
            value={newAllowed ? "1" : "0"}
            onChange={(e) => setNewAllowed(e.target.value === "1")}
            className="bg-secondary border border-border rounded-md px-3 py-2 text-sm"
          >
            <option value="1">Allow</option>
            <option value="0">Deny</option>
          </select>
          <Button onClick={onCreate}>Save</Button>
        </div>
      </section>

      <section className="bg-card border border-border rounded-lg divide-y divide-border">
        {permissions.map((p) => (
          <div key={p.id} className="p-4 flex items-center gap-3">
            <div>
              <div className="font-medium">{p.username}</div>
              <div className="text-xs text-muted-foreground">
                {p.feature_display || p.feature} • {p.allowed ? "Allowed" : "Denied"}
              </div>
            </div>
            <div className="ml-auto flex gap-2">
              <Button size="sm" variant="outline" onClick={() => toggleAllowed(p.id, p.allowed)}>
                Toggle
              </Button>
              <Button size="sm" variant="destructive" onClick={() => remove(p.id)}>
                Delete
              </Button>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
