import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createAccessGroup, deleteAccessGroup, fetchAccessGroups, fetchAccessUsers, updateAccessGroup } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function SummaryPill({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-full border border-transparent bg-background/30 px-3 py-1 text-xs text-muted-foreground">
      <span className="font-medium text-foreground">{value}</span> {label}
    </div>
  );
}

export default function SettingsGroupsPage() {
  const queryClient = useQueryClient();
  const [newName, setNewName] = useState("");
  const [newMembers, setNewMembers] = useState<number[]>([]);

  const { data: groupsData, isLoading, error } = useQuery({ queryKey: ["access", "groups"], queryFn: fetchAccessGroups });
  const { data: usersData } = useQuery({ queryKey: ["access", "users"], queryFn: fetchAccessUsers });

  const groups = groupsData?.groups || [];
  const users = usersData?.users || [];

  const reload = async () => {
    await queryClient.invalidateQueries({ queryKey: ["access", "groups"] });
  };

  const toggleMember = (id: number) => {
    setNewMembers((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const onCreate = async () => {
    if (!newName.trim()) return;
    await createAccessGroup({ name: newName.trim(), members: newMembers });
    setNewName("");
    setNewMembers([]);
    // setMemberSearch("");
    await reload();
  };

  const renameGroup = async (id: number, name: string) => {
    const next = prompt("New group name", name);
    if (!next || next === name) return;
    await updateAccessGroup(id, { name: next });
    await reload();
  };

  const deleteGroup = async (id: number, name: string) => {
    if (!confirm(`Delete group ${name}?`)) return;
    await deleteAccessGroup(id);
    await reload();
  };

  if (isLoading) return <div className="p-6 text-sm text-muted-foreground">Loading groups...</div>;
  if (error) return <div className="p-6 text-sm text-destructive">Failed to load groups.</div>;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold text-foreground">Groups</h1>

      <section className="bg-card border border-border rounded-lg p-4 space-y-3">
        <h2 className="text-sm font-medium">Create Group</h2>
        <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Group name" />
        <div className="flex flex-wrap gap-2">
          {users.map((u) => (
            <button
              key={u.id}
              className={`px-2 py-1 text-xs rounded border ${newMembers.includes(u.id) ? "border-primary text-primary" : "border-border text-muted-foreground"}`}
              onClick={() => toggleMember(u.id)}
              type="button"
            >
              {u.username}
            </button>
          ))}
        </div>
        <Button onClick={onCreate} disabled={!newName.trim()}>
          Create Group
        </Button>
      </section>

      <section className="bg-card border border-border rounded-lg divide-y divide-border">
        {groups.map((g) => (
          <div key={g.id} className="p-4 flex items-center gap-3">
            <div>
              <div className="font-medium">{g.name}</div>
              <div className="text-xs text-muted-foreground">Members: {g.member_count}</div>
            </div>
            <div className="ml-auto flex gap-2">
              <Button size="sm" variant="outline" onClick={() => renameGroup(g.id, g.name)}>
                Rename
              </Button>
              <Button size="sm" variant="destructive" onClick={() => deleteGroup(g.id, g.name)}>
                Delete
              </Button>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
