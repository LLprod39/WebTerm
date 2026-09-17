import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Shield, UserPlus } from "lucide-react";

import {
  fetchKubernetesAccessCandidates,
  fetchKubernetesClusterAccess,
  fetchKubernetesClusters,
  fetchKubernetesNamespaces,
  grantKubernetesClusterAccess,
  revokeKubernetesClusterAccess,
} from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";

export function ClusterAccessAdminPanel() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [clusterId, setClusterId] = useState("");
  const [userQuery, setUserQuery] = useState("");
  const [selectedUser, setSelectedUser] = useState("");
  const [namespaceFilter, setNamespaceFilter] = useState<string[]>([]);

  const clustersQuery = useQuery({
    queryKey: ["kubernetes", "clusters", "admin-access"],
    queryFn: fetchKubernetesClusters,
    staleTime: 15_000,
  });
  const clusters = clustersQuery.data?.clusters || [];

  const grantsQuery = useQuery({
    queryKey: ["kubernetes", "access", clusterId],
    queryFn: () => fetchKubernetesClusterAccess(clusterId),
    enabled: Boolean(clusterId),
    staleTime: 10_000,
  });

  const namespacesQuery = useQuery({
    queryKey: ["kubernetes", "namespaces", clusterId, "access"],
    queryFn: () => fetchKubernetesNamespaces(clusterId),
    enabled: Boolean(clusterId),
    staleTime: 15_000,
  });

  const candidatesQuery = useQuery({
    queryKey: ["kubernetes", "access-candidates", userQuery],
    queryFn: () => fetchKubernetesAccessCandidates(userQuery),
    enabled: userQuery.trim().length >= 1,
    staleTime: 10_000,
  });

  const namespaces = useMemo(
    () => namespacesQuery.data?.namespaces || [],
    [namespacesQuery.data],
  );

  const grantMutation = useMutation({
    mutationFn: () =>
      grantKubernetesClusterAccess(clusterId, {
        user: selectedUser,
        namespaces: namespaceFilter,
        can_view_logs: true,
        can_exec: false,
      }),
    onSuccess: async () => {
      setSelectedUser("");
      setNamespaceFilter([]);
      await queryClient.invalidateQueries({ queryKey: ["kubernetes", "access", clusterId] });
      toast({ description: "Доступ выдан." });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const revokeMutation = useMutation({
    mutationFn: (grantId: number) => revokeKubernetesClusterAccess(clusterId, grantId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["kubernetes", "access", clusterId] });
      toast({ description: "Доступ отозван." });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const toggleNamespace = (name: string) => {
    setNamespaceFilter((prev) =>
      prev.includes(name) ? prev.filter((item) => item !== name) : [...prev, name],
    );
  };

  return (
    <SectionCard
      title="Доступ пользователей"
      description="Выдайте пользователю платформенный кластер. Пустой список областей = весь кластер. Личные kubeconfig пользователей здесь не управляются."
      icon={<Shield className="h-4 w-4" />}
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div className="space-y-3">
          <label className="space-y-1.5 block">
            <span className="text-xs text-muted-foreground">Кластер</span>
            <Select value={clusterId || "__none__"} onValueChange={(value) => setClusterId(value === "__none__" ? "" : value)}>
              <SelectTrigger className="h-10">
                <SelectValue placeholder="Выберите кластер" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__" disabled>
                  Выберите кластер
                </SelectItem>
                {clusters.map((cluster) => (
                  <SelectItem key={cluster.id} value={cluster.id}>
                    {cluster.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>

          <label className="space-y-1.5 block">
            <span className="text-xs text-muted-foreground">Поиск пользователя</span>
            <Input
              value={userQuery}
              onChange={(event) => setUserQuery(event.target.value)}
              placeholder="username / email"
              autoComplete="off"
            />
          </label>

          {candidatesQuery.data?.candidates?.length ? (
            <div className="space-y-1">
              {candidatesQuery.data.candidates.map((candidate) => (
                <button
                  key={candidate.id}
                  type="button"
                  className={`flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm ${
                    selectedUser === candidate.username
                      ? "border-primary bg-primary/5"
                      : "border-border bg-background"
                  }`}
                  onClick={() => setSelectedUser(candidate.username)}
                >
                  <span className="font-medium text-foreground">{candidate.username}</span>
                  <span className="text-xs text-muted-foreground">{candidate.email || "—"}</span>
                </button>
              ))}
            </div>
          ) : null}

          {clusterId && namespaces.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">
                Области (необязательно). Если ничего не выбрать — весь кластер.
              </div>
              <div className="flex max-h-40 flex-wrap gap-2 overflow-auto">
                {namespaces.map((ns) => {
                  const active = namespaceFilter.includes(ns.name);
                  return (
                    <button
                      key={ns.id || ns.name}
                      type="button"
                      className={`rounded-full border px-2.5 py-1 text-xs ${
                        active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"
                      }`}
                      onClick={() => toggleNamespace(ns.name)}
                    >
                      {ns.name}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : null}

          <Button
            type="button"
            className="gap-2"
            disabled={!clusterId || !selectedUser || grantMutation.isPending}
            onClick={() => grantMutation.mutate()}
          >
            {grantMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <UserPlus className="h-4 w-4" aria-hidden />
            )}
            Выдать доступ
          </Button>
        </div>

        <div className="space-y-3">
          <div className="text-sm font-semibold text-foreground">Текущие выдачи</div>
          {!clusterId ? (
            <p className="text-sm text-muted-foreground">Сначала выберите кластер.</p>
          ) : grantsQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">Загрузка…</p>
          ) : (grantsQuery.data?.grants || []).length === 0 ? (
            <p className="text-sm text-muted-foreground">Пока никому не выдано.</p>
          ) : (
            <ul className="space-y-2">
              {(grantsQuery.data?.grants || []).map((grant) => (
                <li
                  key={grant.id}
                  className="flex flex-col gap-2 rounded-lg border border-border px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-foreground">{grant.username}</span>
                      <StatusBadge
                        label={grant.is_active ? "active" : "expired"}
                        tone={grant.is_active ? "success" : "warning"}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {grant.namespaces.length
                        ? `Области: ${grant.namespaces.join(", ")}`
                        : "Весь кластер"}
                    </p>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="text-destructive"
                    disabled={revokeMutation.isPending}
                    onClick={() => revokeMutation.mutate(grant.id)}
                  >
                    Отозвать
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </SectionCard>
  );
}
