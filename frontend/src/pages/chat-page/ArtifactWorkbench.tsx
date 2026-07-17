import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileCode2, Loader2, Save } from "lucide-react";

import {
  fetchChatArtifacts,
  updateChatArtifact,
  type ChatArtifact,
} from "@/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";

export function ArtifactWorkbench({
  chatId,
  open,
  onClose,
}: {
  chatId: number | null;
  open: boolean;
  onClose: () => void;
}) {
  const { lang } = useI18n();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  const query = useQuery({
    queryKey: ["assistant", "artifacts", chatId],
    queryFn: () => fetchChatArtifacts(chatId as number),
    enabled: Boolean(chatId && open),
    staleTime: 5_000,
  });

  const artifacts = query.data?.artifacts || [];
  const selected = artifacts.find((a) => a.id === selectedId) || artifacts[0] || null;

  useEffect(() => {
    if (selected) {
      setSelectedId(selected.id);
      setDraft(selected.content);
    } else {
      setDraft("");
    }
  }, [selected?.id, selected?.version]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveMutation = useMutation({
    mutationFn: () =>
      updateChatArtifact(chatId as number, {
        id: selected!.id,
        content: draft,
        bump_version: true,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["assistant", "artifacts", chatId] });
      toast({
        title: localize(lang, "Артефакт", "Artifact"),
        description: localize(lang, "Сохранена новая версия", "New version saved"),
      });
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Ошибка", "Error"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
  });

  if (!open || !chatId) return null;

  return (
    <aside className="flex w-full max-w-md shrink-0 flex-col border-l border-border/70 bg-card/50">
      <div className="flex h-12 items-center justify-between border-b border-border/70 px-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <FileCode2 className="h-4 w-4 text-primary" />
          {localize(lang, "Верстак", "Workbench")}
        </div>
        <Button size="sm" variant="ghost" onClick={onClose}>
          {localize(lang, "Скрыть", "Hide")}
        </Button>
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="w-36 shrink-0 overflow-y-auto border-r border-border/60 p-2">
          {query.isLoading ? (
            <div className="flex items-center gap-1 p-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
            </div>
          ) : null}
          {!artifacts.length && !query.isLoading ? (
            <p className="px-1 py-3 text-2xs text-muted-foreground">
              {localize(lang, "Пока пусто", "Empty")}
            </p>
          ) : null}
          {artifacts.map((art: ChatArtifact) => (
            <button
              key={art.id}
              type="button"
              onClick={() => setSelectedId(art.id)}
              className={cn(
                "mb-1 w-full rounded-sm px-2 py-1.5 text-left text-2xs transition-colors",
                selected?.id === art.id
                  ? "bg-primary/15 text-foreground"
                  : "text-muted-foreground hover:bg-secondary/50",
              )}
            >
              <div className="truncate font-medium">{art.title || art.kind}</div>
              <div className="font-mono opacity-70">
                {art.kind} · v{art.version}
              </div>
            </button>
          ))}
        </div>
        <div className="flex min-w-0 flex-1 flex-col p-2">
          {selected ? (
            <>
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="min-w-0 truncate text-xs font-medium">{selected.title}</div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={saveMutation.isPending || draft === selected.content}
                  onClick={() => saveMutation.mutate()}
                >
                  {saveMutation.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Save className="h-3.5 w-3.5" />
                  )}
                  {localize(lang, "Сохранить", "Save")}
                </Button>
              </div>
              <Textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                className="min-h-0 flex-1 resize-none font-mono text-2xs leading-5"
              />
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center text-xs text-muted-foreground">
              {localize(lang, "Выберите артефакт", "Select an artifact")}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
