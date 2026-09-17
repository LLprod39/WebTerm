import { useCallback, useMemo, useRef, useState } from "react";

import {
  commitGitLabPlaybookProject,
  previewGitLabPlaybookProject,
  type CommitPlaybookBundleMetadata,
  type CommitPlaybookBundleResponse,
  type GitLabProjectSource,
  type GitLabProjectSourceInput,
  type PlaybookBundlePreview,
} from "@/api/playbook-bundles";

type GitLabImportStatus = "idle" | "previewing" | "ready" | "committing" | "success" | "error";

const emptySource = (): GitLabProjectSourceInput => ({ project_url: "", ref: "", path: "", token: "" });
const emptyMetadata = (): CommitPlaybookBundleMetadata => ({
  entrypoint: "",
  name: "",
  description: "",
  category: "custom",
  visibility: "private",
  tags: [],
});

export function usePlaybookGitLabImport(options: {
  onCommitted?: (result: CommitPlaybookBundleResponse) => void | Promise<void>;
} = {}) {
  const sequence = useRef(0);
  const [status, setStatus] = useState<GitLabImportStatus>("idle");
  const [source, setSourceState] = useState<GitLabProjectSourceInput>(emptySource);
  const [resolvedSource, setResolvedSource] = useState<GitLabProjectSource | null>(null);
  const [preview, setPreview] = useState<PlaybookBundlePreview | null>(null);
  const [metadata, setMetadata] = useState<CommitPlaybookBundleMetadata>(emptyMetadata);
  const [error, setError] = useState("");
  const [result, setResult] = useState<CommitPlaybookBundleResponse | null>(null);

  const reset = useCallback(() => {
    sequence.current += 1;
    setStatus("idle");
    setSourceState(emptySource());
    setResolvedSource(null);
    setPreview(null);
    setMetadata(emptyMetadata());
    setError("");
    setResult(null);
  }, []);

  const updateSource = useCallback((patch: Partial<GitLabProjectSourceInput>) => {
    sequence.current += 1;
    setSourceState((current) => ({ ...current, ...patch }));
    setResolvedSource(null);
    setPreview(null);
    setResult(null);
    setError("");
    setStatus("idle");
  }, []);

  const previewProject = useCallback(async (requestedEntrypoint = "") => {
    if (!source.project_url.trim()) return null;
    const request = sequence.current + 1;
    sequence.current = request;
    setStatus("previewing");
    setError("");
    try {
      if (requestedEntrypoint) setPreview(null);
      const response = await previewGitLabPlaybookProject({ ...source, ...(requestedEntrypoint ? { entrypoint: requestedEntrypoint } : {}) });
      if (sequence.current !== request) return null;
      const entrypoint = response.preview.selected_entrypoint ||
        (response.preview.entrypoints.length === 1 ? response.preview.entrypoints[0].path : "");
      const fallbackName = response.source.project.split("/").pop() || "Ansible project";
      setResolvedSource(response.source);
      setPreview(response.preview);
      setMetadata((current) => requestedEntrypoint ? { ...current, entrypoint } : {
          entrypoint,
          name: response.preview.manifest.name?.trim() || fallbackName,
          description: response.preview.manifest.description?.trim() || "",
          category: "custom",
          visibility: "private",
          tags: Array.isArray(response.preview.manifest.tags) ? response.preview.manifest.tags : [],
        });
      setStatus("ready");
      return response.preview;
    } catch (caught) {
      if (sequence.current !== request) return null;
      setStatus("error");
      setError(errorMessage(caught));
      return null;
    }
  }, [source]);

  const selectEntrypoint = useCallback((entrypoint: string) => previewProject(entrypoint), [previewProject]);

  const updateMetadata = useCallback((patch: Partial<CommitPlaybookBundleMetadata>) => {
    setMetadata((current) => ({ ...current, ...patch, visibility: "private" }));
    setError("");
    setStatus((current) => current === "error" && preview ? "ready" : current);
  }, [preview]);

  const commit = useCallback(async () => {
    if (!preview?.safe_to_commit || !metadata.entrypoint || !metadata.name.trim()) return null;
    const request = sequence.current + 1;
    sequence.current = request;
    setStatus("committing");
    setError("");
    try {
      const response = await commitGitLabPlaybookProject(source, { ...metadata, visibility: "private" }, preview.content_hash);
      if (sequence.current !== request) return null;
      setResult(response);
      setStatus("success");
      await options.onCommitted?.(response);
      return response;
    } catch (caught) {
      if (sequence.current !== request) return null;
      setStatus("error");
      setError(errorMessage(caught));
      return null;
    }
  }, [metadata, options, preview, source]);

  const busy = status === "previewing" || status === "committing";
  const canPreview = Boolean(source.project_url.trim() && !busy);
  const canCommit = Boolean(preview?.safe_to_commit && metadata.entrypoint && metadata.name.trim() && !busy && !result);
  const progress = useMemo(() => {
    if (status === "success") return 100;
    if (status === "committing") return 80;
    if (preview) return 55;
    if (status === "previewing") return 25;
    return 0;
  }, [preview, status]);

  return {
    status,
    source,
    resolvedSource,
    preview,
    metadata,
    error,
    result,
    busy,
    canPreview,
    canCommit,
    progress,
    reset,
    updateSource,
    previewProject,
    selectEntrypoint,
    updateMetadata,
    commit,
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
