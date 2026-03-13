import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createAccessUser,
  deleteAccessUser,
  fetchAccessGroups,
  fetchAccessUsers,
  setAccessUserPassword,
  updateAccessUser,
  type AccessUser,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

function emptyForm() {
  return {
    username: "",
    email: "",
    password: "",
    is_staff: false,
    is_active: true,
    access_profile: "server_only",
    groups: [] as number[],
  };
}

export default function SettingsUsersPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editing, setEditing] = useState<Record<string, unknown>>({});

  const { data: usersData, isLoading, error } = useQuery({ queryKey: ["access", "users"], queryFn: fetchAccessUsers });
  const { data: groupsData } = useQuery({ queryKey: ["access", "groups"], queryFn: fetchAccessGroups });

  const users = useMemo(() => usersData?.users ?? [], [usersData?.users]);
  const groups = useMemo(() => groupsData?.groups ?? [], [groupsData?.groups]);

  const selectedGroupsLabel = useMemo(() => {
    const selected = groups.filter((g) => form.groups.includes(g.id));
    return selected.map((g) => g.name).join(", ");
  }, [form.groups, groups]);

  const reload = async () => {
    await queryClient.invalidateQueries({ queryKey: ["access", "users"] });
    await queryClient.invalidateQueries({ queryKey: ["access", "groups"] });
  };

  const onCreate = async () => {
    setSaving(true);
    try {
      await createAccessUser(form);
      setForm(emptyForm());
      await reload();
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (u: AccessUser) => {
    setEditingId(u.id);
    setEditing({
      username: u.username,
      email: u.email,
      is_staff: u.is_staff,
      is_active: u.is_active,
      access_profile: u.access_profile || "custom",
      groups: (u.groups || []).map((g) => g.id),
    });
  };

  const saveEdit = async () => {
    if (!editingId) return;
    await updateAccessUser(editingId, editing);
    setEditingId(null);
    setEditing({});
    await reload();
  };

  const removeUser = async (u: AccessUser) => {
    if (!confirm(`Delete user ${u.username}?`)) return;
    await deleteAccessUser(u.id);
    await reload();
  };

  const resetPassword = async (u: AccessUser) => {
    const password = prompt(`New password for ${u.username}`);
    if (!password) return;
    await setAccessUserPassword(u.id, password);
    alert("Password updated");
  };

  const toggleGroup = (source: number[], id: number) => {
    if (source.includes(id)) return source.filter((x) => x !== id);
    return [...source, id];
  };

  if (isLoading) return <div className="p-6 text-sm text-muted-foreground">Loading users...</div>;
  if (error) return <div className="p-6 text-sm text-destructive">Failed to load users.</div>;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold text-foreground">Users</h1>

      <section className="bg-card border border-border rounded-lg p-4 space-y-3">
        <h2 className="text-sm font-medium text-foreground">Create User</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Input placeholder="Username" value={form.username} onChange={(e) => setForm((s) => ({ ...s, username: e.target.value }))} />
          <Input placeholder="Email" value={form.email} onChange={(e) => setForm((s) => ({ ...s, email: e.target.value }))} />
          <Input placeholder="Password" type="password" value={form.password} onChange={(e) => setForm((s) => ({ ...s, password: e.target.value }))} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
          <label className="text-xs text-muted-foreground">Profile</label>
          <select
            value={form.access_profile}
            onChange={(e) => setForm((s) => ({ ...s, access_profile: e.target.value }))}
            className="bg-secondary border border-border rounded-md px-3 py-2 text-sm"
          >
            <option value="server_only">Server only</option>
            <option value="admin_full">Admin full</option>
            <option value="custom">Custom</option>
            <option value="reset_defaults">Reset defaults</option>
          </select>
          <div className="flex items-center gap-4">
            <label className="text-sm flex items-center gap-2">Staff <Switch checked={form.is_staff} onCheckedChange={(v) => setForm((s) => ({ ...s, is_staff: v }))} /></label>
            <label className="text-sm flex items-center gap-2">Active <Switch checked={form.is_active} onCheckedChange={(v) => setForm((s) => ({ ...s, is_active: v }))} /></label>
          </div>
        </div>
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">Groups: {selectedGroupsLabel || "none"}</p>
          <div className="flex flex-wrap gap-2">
            {groups.map((g) => (
              <button
                key={g.id}
                className={`px-2 py-1 text-xs rounded border ${form.groups.includes(g.id) ? "border-primary text-primary" : "border-border text-muted-foreground"}`}
                onClick={() => setForm((s) => ({ ...s, groups: toggleGroup(s.groups, g.id) }))}
                type="button"
              >
                {g.name}
              </button>
            ))}
          </div>
        </div>
        <Button onClick={onCreate} disabled={saving || !form.username || !form.password}>
          {saving ? "Creating..." : "Create User"}
        </Button>
      </section>

      <section className="bg-card border border-border rounded-lg divide-y divide-border">
        {users.map((u) => {
          const isEditing = editingId === u.id;
          const e = editing as {
            username?: string;
            email?: string;
            is_staff?: boolean;
            is_active?: boolean;
            access_profile?: string;
            groups?: number[];
          };
          return (
            <div key={u.id} className="p-4 space-y-3">
              {!isEditing ? (
                <>
                  <div className="flex items-center gap-3">
                    <div className="font-medium">{u.username}</div>
                    <div className="text-xs text-muted-foreground">{u.email || "-"}</div>
                    <div className="ml-auto text-xs text-muted-foreground">{u.access_profile || "custom"}</div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => startEdit(u)}>
                      Edit
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => resetPassword(u)}>
                      Password
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => removeUser(u)}>
                      Delete
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <Input value={e.username || ""} onChange={(ev) => setEditing((s) => ({ ...s, username: ev.target.value }))} />
                    <Input value={e.email || ""} onChange={(ev) => setEditing((s) => ({ ...s, email: ev.target.value }))} />
                    <select
                      value={e.access_profile || "custom"}
                      onChange={(ev) => setEditing((s) => ({ ...s, access_profile: ev.target.value }))}
                      className="bg-secondary border border-border rounded-md px-3 py-2 text-sm"
                    >
                      <option value="server_only">Server only</option>
                      <option value="admin_full">Admin full</option>
                      <option value="custom">Custom</option>
                      <option value="reset_defaults">Reset defaults</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-4">
                    <label className="text-sm flex items-center gap-2">
                      Staff
                      <Switch checked={!!e.is_staff} onCheckedChange={(v) => setEditing((s) => ({ ...s, is_staff: v }))} />
                    </label>
                    <label className="text-sm flex items-center gap-2">
                      Active
                      <Switch checked={!!e.is_active} onCheckedChange={(v) => setEditing((s) => ({ ...s, is_active: v }))} />
                    </label>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={saveEdit}>
                      Save
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>
                      Cancel
                    </Button>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </section>
    </div>
  );
}
