import { useCallback, useMemo, useRef, useState } from "react";

import {
  commitRawPlaybook,
  previewRawPlaybook,
  type RawPlaybookImportCommit,
  type RawPlaybookImportPreview,
} from "@/api/playbooks";

type YamlImportStatus = "idle" | "previewing" | "ready" | "committing" | "success" | "error";

export function usePlaybookYamlImport(options: {
  onCommitted?: (result: RawPlaybookImportCommit) => void | Promise<void>;
} = {}) {
  const sequence = useRef(0);
  const [status, setStatus] = useState<YamlImportStatus>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [content, setContent] = useState("");
  const [preview, setPreview] = useState<RawPlaybookImportPreview | null>(null);
  const [result, setResult] = useState<RawPlaybookImportCommit | null>(null);
  const [error, setError] = useState("");

  const reset = useCallback(() => {
    sequence.current += 1;
    setStatus("idle");
    setFile(null);
    setContent("");
    setPreview(null);
    setResult(null);
    setError("");
  }, []);

  const selectFile = useCallback(async (nextFile: File) => {
    const request = sequence.current + 1;
    sequence.current = request;
    setFile(nextFile);
    setPreview(null);
    setResult(null);
    setError("");
    if (!/\.ya?ml$/i.test(nextFile.name)) {
      setStatus("error");
      setError("Choose a .yml or .yaml Ansible playbook");
      return null;
    }
    setStatus("previewing");
    try {
      const source = await nextFile.text();
      const response = await previewRawPlaybook(source, nextFile.name);
      if (sequence.current !== request) return null;
      setContent(source);
      setPreview(response);
      setStatus("ready");
      return response;
    } catch (caught) {
      if (sequence.current !== request) return null;
      setStatus("error");
      setError(caught instanceof Error ? caught.message : String(caught));
      return null;
    }
  }, []);

  const commit = useCallback(async () => {
    if (!file || !content || !preview?.safe_to_commit) return null;
    const request = sequence.current + 1;
    sequence.current = request;
    setStatus("committing");
    setError("");
    try {
      const response = await commitRawPlaybook(content, file.name, preview.content_hash);
      if (sequence.current !== request) return null;
      setResult(response);
      setStatus("success");
      await options.onCommitted?.(response);
      return response;
    } catch (caught) {
      if (sequence.current !== request) return null;
      setStatus("error");
      setError(caught instanceof Error ? caught.message : String(caught));
      return null;
    }
  }, [content, file, options, preview]);

  const busy = status === "previewing" || status === "committing";
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
    result,
    error,
    busy,
    progress,
    canCommit: Boolean(preview?.safe_to_commit && !busy && !result),
    reset,
    selectFile,
    commit,
  };
}
