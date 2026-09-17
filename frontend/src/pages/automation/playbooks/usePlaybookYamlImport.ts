import { useCallback, useMemo, useRef, useState } from "react";

import {
  commitRawPlaybook,
  previewRawPlaybook,
  type RawPlaybookImportCommit,
  type RawPlaybookImportPreview,
} from "@/api/playbooks";

type YamlImportStatus = "idle" | "previewing" | "ready" | "committing" | "success" | "error";

const DEFAULT_FILENAME = "playbook.yml";

export function usePlaybookYamlImport(options: {
  onCommitted?: (result: RawPlaybookImportCommit) => void | Promise<void>;
} = {}) {
  const sequence = useRef(0);
  const [status, setStatus] = useState<YamlImportStatus>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [filename, setFilename] = useState(DEFAULT_FILENAME);
  const [pasteText, setPasteText] = useState("");
  const [content, setContent] = useState("");
  const [preview, setPreview] = useState<RawPlaybookImportPreview | null>(null);
  const [result, setResult] = useState<RawPlaybookImportCommit | null>(null);
  const [error, setError] = useState("");

  const reset = useCallback(() => {
    sequence.current += 1;
    setStatus("idle");
    setFile(null);
    setFilename(DEFAULT_FILENAME);
    setPasteText("");
    setContent("");
    setPreview(null);
    setResult(null);
    setError("");
  }, []);

  const previewSource = useCallback(async (source: string, nextFilename: string, nextFile: File | null = null) => {
    const request = sequence.current + 1;
    sequence.current = request;
    setFile(nextFile);
    setFilename(nextFilename);
    setPreview(null);
    setResult(null);
    setError("");
    if (!source.trim()) {
      setStatus("error");
      setError("Paste or upload an Ansible playbook YAML");
      return null;
    }
    if (!/\.ya?ml$/i.test(nextFilename)) {
      setStatus("error");
      setError("Choose a .yml or .yaml Ansible playbook");
      return null;
    }
    setStatus("previewing");
    try {
      const response = await previewRawPlaybook(source, nextFilename);
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

  const selectFile = useCallback(async (nextFile: File) => {
    const source = await nextFile.text();
    setPasteText(source);
    return previewSource(source, nextFile.name, nextFile);
  }, [previewSource]);

  const previewPaste = useCallback(async () => {
    const source = pasteText;
    const name = filename.trim() || DEFAULT_FILENAME;
    return previewSource(source, /\.ya?ml$/i.test(name) ? name : `${name}.yml`, null);
  }, [filename, pasteText, previewSource]);

  const commit = useCallback(async () => {
    if (!content || !preview?.safe_to_commit) return null;
    const request = sequence.current + 1;
    sequence.current = request;
    setStatus("committing");
    setError("");
    try {
      const response = await commitRawPlaybook(content, filename || DEFAULT_FILENAME, preview.content_hash);
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
  }, [content, filename, options, preview]);

  const busy = status === "previewing" || status === "committing";
  const progress = useMemo(() => {
    if (status === "success") return 100;
    if (status === "committing") return 82;
    if (preview) return 55;
    if (status === "previewing") return 28;
    return file || pasteText.trim() ? 12 : 0;
  }, [file, pasteText, preview, status]);

  return {
    status,
    file,
    filename,
    pasteText,
    preview,
    result,
    error,
    busy,
    progress,
    canCommit: Boolean(preview?.safe_to_commit && !busy && !result),
    canPreviewPaste: Boolean(pasteText.trim() && !busy && !result),
    reset,
    selectFile,
    setPasteText,
    setFilename,
    previewPaste,
    commit,
  };
}
