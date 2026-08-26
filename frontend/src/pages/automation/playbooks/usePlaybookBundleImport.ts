import { useCallback, useMemo, useRef, useState } from "react";

import {
  commitPlaybookBundle,
  isSupportedPlaybookBundleFile,
  previewPlaybookBundle,
  type CommitPlaybookBundleMetadata,
  type CommitPlaybookBundleResponse,
  type PlaybookBundlePreview,
} from "@/api/playbook-bundles";

export type PlaybookBundleImportStatus =
  | "idle"
  | "previewing"
  | "ready"
  | "committing"
  | "success"
  | "error";

const emptyMetadata = (): CommitPlaybookBundleMetadata => ({
  entrypoint: "",
  project_path: "",
  name: "",
  description: "",
  category: "custom",
  visibility: "private",
  tags: [],
});

interface UsePlaybookBundleImportOptions {
  onCommitted?: (result: CommitPlaybookBundleResponse) => void | Promise<void>;
}

export function usePlaybookBundleImport(options: UsePlaybookBundleImportOptions = {}) {
  const requestSequence = useRef(0);
  const [status, setStatus] = useState<PlaybookBundleImportStatus>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PlaybookBundlePreview | null>(null);
  const [metadata, setMetadata] = useState<CommitPlaybookBundleMetadata>(emptyMetadata);
  const [error, setError] = useState("");
  const [errorStage, setErrorStage] = useState<"file" | "preview" | "commit" | null>(null);
  const [result, setResult] = useState<CommitPlaybookBundleResponse | null>(null);

  const reset = useCallback(() => {
    requestSequence.current += 1;
    setStatus("idle");
    setFile(null);
    setPreview(null);
    setMetadata(emptyMetadata());
    setError("");
    setErrorStage(null);
    setResult(null);
  }, []);

  const selectFile = useCallback(async (nextFile: File) => {
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setFile(nextFile);
    setPreview(null);
    setResult(null);
    setError("");
    setErrorStage(null);

    if (!isSupportedPlaybookBundleFile(nextFile)) {
      setStatus("error");
      setErrorStage("file");
      setError("Choose a .zip, .tar, or .tar.gz project bundle");
      return null;
    }

    setStatus("previewing");
    try {
      const response = await previewPlaybookBundle(nextFile);
      if (requestSequence.current !== sequence) return null;
      const selectedEntrypoint =
        response.preview.selected_entrypoint ||
        (response.preview.entrypoints.length === 1 ? response.preview.entrypoints[0].path : "");
      setPreview(response.preview);
      setMetadata(metadataFromPreview(response.preview, nextFile.name, selectedEntrypoint));
      setStatus("ready");
      return response.preview;
    } catch (caught) {
      if (requestSequence.current !== sequence) return null;
      setStatus("error");
      setErrorStage("preview");
      setError(errorMessage(caught));
      return null;
    }
  }, []);

  const retryPreview = useCallback(async () => {
    if (!file) return null;
    return selectFile(file);
  }, [file, selectFile]);

  const selectEntrypoint = useCallback(async (entrypoint: string) => {
    if (!file || !entrypoint || entrypoint === metadata.entrypoint) return preview;
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setStatus("previewing");
    setPreview(null);
    setError("");
    setErrorStage(null);
    try {
      const response = await previewPlaybookBundle(file, entrypoint, metadata.project_path || "");
      if (requestSequence.current !== sequence) return null;
      const selectedEntrypoint = response.preview.selected_entrypoint || entrypoint;
      setPreview(response.preview);
      setMetadata((current) => ({
        ...current,
        entrypoint: selectedEntrypoint,
        project_path: response.preview.project_path || current.project_path || "",
      }));
      setStatus("ready");
      return response.preview;
    } catch (caught) {
      if (requestSequence.current !== sequence) return null;
      setStatus("error");
      setErrorStage("preview");
      setError(errorMessage(caught));
      return null;
    }
  }, [file, metadata.entrypoint, metadata.project_path, preview]);

  const selectProjectPath = useCallback(async (projectPath: string) => {
    const normalized = projectPath.trim().replace(/^\/+|\/+$/g, "");
    if (!file || normalized === (metadata.project_path || "")) return preview;
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setStatus("previewing");
    setPreview(null);
    setError("");
    setErrorStage(null);
    try {
      const response = await previewPlaybookBundle(file, "", normalized);
      if (requestSequence.current !== sequence) return null;
      const selectedEntrypoint = response.preview.selected_entrypoint
        || (response.preview.entrypoints.length === 1 ? response.preview.entrypoints[0].path : "");
      setPreview(response.preview);
      setMetadata((current) => ({
        ...current,
        entrypoint: selectedEntrypoint,
        project_path: response.preview.project_path || normalized,
      }));
      setStatus("ready");
      return response.preview;
    } catch (caught) {
      if (requestSequence.current !== sequence) return null;
      setStatus("error");
      setErrorStage("preview");
      setError(errorMessage(caught));
      return null;
    }
  }, [file, metadata.project_path, preview]);

  const updateMetadata = useCallback((patch: Partial<CommitPlaybookBundleMetadata>) => {
    setMetadata((current) => ({ ...current, ...patch, visibility: "private" }));
    setError((current) => (current ? "" : current));
    setErrorStage((current) => (current === "commit" ? null : current));
    setStatus((current) => (current === "error" && preview ? "ready" : current));
  }, [preview]);

  const commit = useCallback(async () => {
    if (!file || !preview || !preview.safe_to_commit || !metadata.entrypoint || !metadata.name.trim()) {
      return null;
    }
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setStatus("committing");
    setError("");
    setErrorStage(null);
    try {
      const response = await commitPlaybookBundle(file, { ...metadata, visibility: "private" }, preview.content_hash);
      if (requestSequence.current !== sequence) return null;
      setResult(response);
      setStatus("success");
      await options.onCommitted?.(response);
      return response;
    } catch (caught) {
      if (requestSequence.current !== sequence) return null;
      setStatus("error");
      setErrorStage("commit");
      setError(errorMessage(caught));
      return null;
    }
  }, [file, metadata, options, preview]);

  const busy = status === "previewing" || status === "committing";
  const canCommit = Boolean(
    file &&
      preview?.safe_to_commit &&
      metadata.entrypoint &&
      metadata.name.trim() &&
      !busy &&
      status !== "success",
  );
  const progress = useMemo(() => {
    if (status === "success") return 100;
    if (status === "committing") return 82;
    if (preview) return 55;
    if (status === "previewing") return 28;
    return file ? 12 : 0;
  }, [file, preview, status]);

  return {
    status,
    file,
    preview,
    metadata,
    error,
    errorStage,
    result,
    busy,
    canCommit,
    progress,
    reset,
    selectFile,
    retryPreview,
    selectEntrypoint,
    selectProjectPath,
    updateMetadata,
    commit,
  };
}

function metadataFromPreview(
  preview: PlaybookBundlePreview,
  filename: string,
  entrypoint: string,
): CommitPlaybookBundleMetadata {
  return {
    entrypoint,
    project_path: preview.project_path || "",
    name: preview.manifest.name?.trim() || filename.replace(/\.(?:tar\.gz|tar|zip)$/i, ""),
    description: preview.manifest.description?.trim() || "",
    category: "custom",
    visibility: "private",
    tags: Array.isArray(preview.manifest.tags) ? preview.manifest.tags : [],
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export type PlaybookBundleImportController = ReturnType<typeof usePlaybookBundleImport>;
