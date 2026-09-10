import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, request } from "@/api/client";
import type { ServerDetail } from "@/api/infrastructure";
import type { TextFile } from "@/api/server-workspace";
import {
  Button,
  ConfirmDialog,
  Drawer,
  ErrorState,
  Feedback,
  Field,
  LoadingState,
} from "@/components/ui";
export interface FileEditorState {
  dirty: boolean;
  pending: boolean;
}
export function TerminalFileEditor({
  server,
  path,
  elevate,
  onClose,
  onStateChange,
}: {
  server: ServerDetail;
  path: string;
  elevate: boolean;
  onClose: () => void;
  onStateChange?: (state: FileEditorState) => void;
}) {
  const [password, setPassword] = useState("");
  const [content, setContent] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [discard, setDiscard] = useState(false);
  const query = useQuery({
    queryKey: ["terminal-file", server.id, path, elevate],
    queryFn: ({ signal }) =>
      request<{ file: TextFile }>(`/servers/api/${server.id}/files/read/`, {
        method: "POST",
        body: JSON.stringify({ path, elevate, sudo_password: password }),
        signal,
      }),
    retry: false,
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const text = content ?? query.data?.file.content ?? "";
  const dirty = text !== (saved ?? query.data?.file.content ?? "");
  const save = useMutation({
    mutationFn: (submitted: string) =>
      api.post(`/servers/api/${server.id}/files/write/`, {
        path,
        content: submitted,
        elevate,
        sudo_password: password,
      }),
    gcTime: 0,
    onSuccess: (_result, submitted) => {
      setSaved(submitted);
      setPassword("");
    },
  });
  useEffect(() => {
    onStateChange?.({ dirty, pending: save.isPending });
  }, [dirty, save.isPending, onStateChange]);
  useEffect(
    () => () => onStateChange?.({ dirty: false, pending: false }),
    [onStateChange],
  );
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty || save.isPending) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, save.isPending]);
  const close = () => {
    if (save.isPending) return;
    if (dirty) setDiscard(true);
    else onClose();
  };
  return (
    <>
      <Drawer
        open
        wide
        title={`Редактор · ${path}`}
        description={
          elevate
            ? "Операция с sudo. Права проверяются сервером."
            : "Файл на удалённом сервере"
        }
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <div className="stack">
          {elevate && (
            <Field
              label="Пароль sudo при необходимости"
              htmlFor="terminal-file-sudo"
            >
              <input
                id="terminal-file-sudo"
                type="password"
                autoComplete="off"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
          )}
          {query.isPending ? (
            <LoadingState />
          ) : query.error ? (
            <ErrorState
              error={query.error}
              retry={() => void query.refetch()}
            />
          ) : (
            <>
              <textarea
                className="mono file-editor"
                aria-label="Содержимое удалённого файла"
                readOnly={!server.capabilities.write_files}
                value={text}
                onChange={(e) => setContent(e.target.value)}
              />
              <div className="spread">
                <span className="muted text-sm">
                  {save.isPending
                    ? "Сохраняем отправленную версию…"
                    : dirty
                      ? "Есть несохранённые изменения"
                      : "Изменения сохранены"}
                </span>
                {server.capabilities.write_files && (
                  <Button
                    variant="primary"
                    loading={save.isPending}
                    disabled={!dirty}
                    onClick={() => save.mutate(text)}
                  >
                    Сохранить файл
                  </Button>
                )}
              </div>
            </>
          )}
          <Feedback error={save.error} />
        </div>
      </Drawer>
      <ConfirmDialog
        open={discard}
        onOpenChange={setDiscard}
        title="Закрыть без сохранения?"
        description="Изменения в файле будут потеряны."
        confirmLabel="Закрыть"
        pending={save.isPending}
        onConfirm={onClose}
      />
    </>
  );
}
