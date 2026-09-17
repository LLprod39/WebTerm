import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileKey2, Loader2, Plus, RefreshCw, Trash2, Upload } from "lucide-react";

import {
  createKubernetesKubeconfigConnection,
  deleteKubernetesConnection,
  fetchKubernetesConnections,
  parseKubernetesKubeconfig,
  rotateKubernetesConnection,
  type KubernetesKubeconfigContext,
} from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/page-shell";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { localize } from "@/lib/i18n";

export function AddClusterPanel({
  lang,
  onConnected,
}: {
  lang: string;
  onConnected?: () => void;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [kubeconfig, setKubeconfig] = useState("");
  const [context, setContext] = useState("");
  const [contexts, setContexts] = useState<KubernetesKubeconfigContext[]>([]);
  const [parseError, setParseError] = useState("");

  const connectionsQuery = useQuery({
    queryKey: ["kubernetes", "connections"],
    queryFn: fetchKubernetesConnections,
    staleTime: 15_000,
  });

  const connections = useMemo(
    () => connectionsQuery.data?.connections || [],
    [connectionsQuery.data],
  );
  const granted = useMemo(
    () => connectionsQuery.data?.granted_clusters || [],
    [connectionsQuery.data],
  );

  useEffect(() => {
    if (!kubeconfig.trim()) {
      setContexts([]);
      setContext("");
      setParseError("");
      return;
    }
    const handle = window.setTimeout(() => {
      void parseKubernetesKubeconfig(kubeconfig)
        .then((result) => {
          if (!result.success) {
            setParseError(result.error || localize(lang, "Не удалось разобрать файл", "Could not parse file"));
            setContexts([]);
            return;
          }
          setParseError("");
          setContexts(result.contexts || []);
          setContext((prev) => prev || result.current_context || result.contexts?.[0]?.name || "");
        })
        .catch((error: Error) => {
          setParseError(error.message);
          setContexts([]);
        });
    }, 350);
    return () => window.clearTimeout(handle);
  }, [kubeconfig, lang]);

  const refreshAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["kubernetes", "connections"] }),
      queryClient.invalidateQueries({ queryKey: ["kubernetes", "clusters"] }),
      queryClient.invalidateQueries({ queryKey: ["kubernetes", "overview"] }),
      queryClient.invalidateQueries({ queryKey: ["kubernetes", "providers"] }),
    ]);
    onConnected?.();
  };

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!kubeconfig.trim()) {
        throw new Error(localize(lang, "Вставьте или загрузите kubeconfig", "Paste or upload a kubeconfig"));
      }
      return createKubernetesKubeconfigConnection({
        name: name.trim() || undefined,
        kubeconfig: kubeconfig.trim(),
        context: context || undefined,
        sync: true,
      });
    },
    onSuccess: async (result) => {
      setKubeconfig("");
      setName("");
      setContext("");
      setContexts([]);
      await refreshAll();
      toast({
        description: result.success
          ? localize(lang, "Кластер подключён. Откройте вкладку Pods.", "Cluster connected. Open the Pods tab.")
          : localize(
              lang,
              result.sync?.error || "Файл сохранён, но sync не удался — проверьте доступ.",
              result.sync?.error || "Saved, but sync failed — check access.",
            ),
        variant: result.success ? "default" : "destructive",
      });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const rotateMutation = useMutation({
    mutationFn: async (connectionId: number) => {
      const next = window.prompt(
        localize(lang, "Вставьте новый kubeconfig целиком", "Paste the new full kubeconfig"),
      );
      if (!next?.trim()) throw new Error(localize(lang, "Отменено", "Cancelled"));
      return rotateKubernetesConnection(connectionId, { kubeconfig: next.trim() });
    },
    onSuccess: async (result) => {
      await refreshAll();
      toast({
        description: result.success
          ? localize(lang, "Файл обновлён.", "File updated.")
          : localize(lang, "Обновлено, но синхронизация завершилась с ошибкой.", "Updated, but sync failed."),
        variant: result.success ? "default" : "destructive",
      });
    },
    onError: (error: Error) => {
      if (error.message === localize(lang, "Отменено", "Cancelled")) return;
      toast({ variant: "destructive", description: error.message });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteKubernetesConnection,
    onSuccess: async () => {
      await refreshAll();
      toast({ description: localize(lang, "Подключение удалено.", "Connection removed.") });
    },
    onError: (error: Error) => toast({ variant: "destructive", description: error.message }),
  });

  const onFile = async (file: File | null) => {
    if (!file) return;
    const text = await file.text();
    setKubeconfig(text);
    if (!name.trim()) {
      setName(file.name.replace(/\.(ya?ml|conf|config)$/i, "").slice(0, 80));
    }
  };

  return (
    <section
      data-ui-slot="add-cluster"
      className="rounded-xl border border-border bg-card px-5 py-6 sm:px-8 sm:py-8"
    >
      <div className="space-y-2">
        <p className="type-label text-muted-foreground">
          {localize(lang, "Мои кластеры", "My clusters")}
        </p>
        <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          {localize(lang, "Добавьте свой кластер через kubeconfig", "Add your cluster with a kubeconfig")}
        </h2>
        <p className="max-w-2xl text-base leading-7 text-muted-foreground">
          {localize(
            lang,
            "Загрузите файл kubeconfig с вашего компьютера (обычно ~/.kube/config). Devtron и Fleet остаются только у администратора в настройках.",
            "Upload a kubeconfig from your machine (usually ~/.kube/config). Devtron and Fleet stay admin-only in settings.",
          )}
        </p>
      </div>

      <form
        className="mt-6 grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          createMutation.mutate();
        }}
      >
        <label className="space-y-1.5">
          <span className="text-sm text-muted-foreground">
            {localize(lang, "Имя (необязательно)", "Name (optional)")}
          </span>
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={localize(lang, "мой-прод", "my-prod")}
            autoComplete="off"
          />
        </label>

        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" className="h-10 gap-2" asChild>
            <label className="cursor-pointer">
              <Upload className="h-4 w-4" aria-hidden />
              {localize(lang, "Выбрать файл", "Choose file")}
              <input
                type="file"
                accept=".yaml,.yml,.conf,.config,text/yaml,text/plain"
                className="sr-only"
                onChange={(event) => void onFile(event.target.files?.[0] || null)}
              />
            </label>
          </Button>
        </div>

        <label className="space-y-1.5">
          <span className="text-sm text-muted-foreground">
            {localize(lang, "Содержимое kubeconfig", "Kubeconfig contents")}
          </span>
          <Textarea
            value={kubeconfig}
            onChange={(event) => setKubeconfig(event.target.value)}
            placeholder={"apiVersion: v1\nkind: Config\n..."}
            className="min-h-[160px] font-mono text-xs"
            required
          />
        </label>

        {parseError ? <p className="text-sm text-destructive">{parseError}</p> : null}

        {contexts.length > 0 ? (
          <label className="space-y-1.5">
            <span className="text-sm text-muted-foreground">
              {localize(lang, "Context", "Context")}
            </span>
            <Select value={context || contexts[0]?.name} onValueChange={setContext}>
              <SelectTrigger className="h-10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {contexts.map((item) => (
                  <SelectItem key={item.name} value={item.name}>
                    {item.name} · {item.server}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
        ) : null}

        <div>
          <Button type="submit" className="h-11 gap-2 px-5" disabled={createMutation.isPending || Boolean(parseError)}>
            {createMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <Plus className="h-4 w-4" aria-hidden />
            )}
            {localize(lang, "Подключить и синхронизировать", "Connect and sync")}
          </Button>
        </div>
      </form>

      <div className="mt-8 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-base font-semibold text-foreground">
            {localize(lang, "Ваши подключения", "Your connections")}
          </h3>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="gap-1.5"
            onClick={() => void connectionsQuery.refetch()}
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />
            {localize(lang, "Обновить список", "Refresh list")}
          </Button>
        </div>

        {connectionsQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">{localize(lang, "Загрузка…", "Loading…")}</p>
        ) : null}

        {!connectionsQuery.isLoading && connections.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-secondary/20 px-4 py-5 text-sm leading-6 text-muted-foreground">
            {localize(
              lang,
              "Пока пусто — загрузите kubeconfig формой выше или попросите администратора выдать доступ.",
              "Empty for now — upload a kubeconfig above or ask an admin to grant access.",
            )}
          </div>
        ) : null}

        <ul className="space-y-2">
          {connections.map((connection) => (
            <li
              key={connection.id}
              className="flex flex-col gap-3 rounded-lg border border-border bg-background/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <FileKey2 className="h-4 w-4 text-muted-foreground" aria-hidden />
                  <span className="font-medium text-foreground">{connection.name}</span>
                  <StatusBadge
                    label={localize(lang, "Мой", "Mine")}
                    tone="info"
                  />
                  {connection.last_error ? (
                    <StatusBadge label={localize(lang, "ошибка", "error")} tone="danger" />
                  ) : (
                    <StatusBadge label={localize(lang, "ok", "ok")} tone="success" />
                  )}
                </div>
                <p className="truncate font-mono text-xs text-muted-foreground">
                  {connection.server || "—"} · {connection.context || "—"}
                </p>
                {connection.last_error ? (
                  <p className="text-xs text-destructive">{connection.last_error}</p>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="gap-1.5"
                  disabled={rotateMutation.isPending}
                  onClick={() => rotateMutation.mutate(connection.id)}
                >
                  <Upload className="h-3.5 w-3.5" aria-hidden />
                  {localize(lang, "Обновить файл", "Update file")}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="gap-1.5 text-destructive"
                  disabled={deleteMutation.isPending}
                  onClick={() => {
                    if (window.confirm(localize(lang, "Удалить это подключение?", "Remove this connection?"))) {
                      deleteMutation.mutate(connection.id);
                    }
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  {localize(lang, "Удалить", "Delete")}
                </Button>
              </div>
            </li>
          ))}
        </ul>

        {granted.length > 0 ? (
          <div className="space-y-2 pt-4">
            <h3 className="text-base font-semibold text-foreground">
              {localize(lang, "Выдано администратором", "Granted by admin")}
            </h3>
            <ul className="space-y-2">
              {granted.map((item) => (
                <li
                  key={item.cluster_id}
                  className="rounded-lg border border-border bg-background/60 px-4 py-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-foreground">{item.cluster_name}</span>
                    <StatusBadge label={localize(lang, "От администратора", "From admin")} tone="warning" />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </section>
  );
}
