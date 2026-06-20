import type { SftpEntry } from "@/lib/api";

import type { SftpBreadcrumbSegment } from "./SftpDirectoryBrowser";
import type { TransferItem } from "../SftpTransferQueue";

let transferSeq = 0;

export function nextTransferId() {
  transferSeq += 1;
  return `transfer_${transferSeq}`;
}

export function buildChildPath(basePath: string, name: string) {
  const normalizedName = String(name || "").trim().replace(/^\/+/, "");
  if (!normalizedName) return basePath;
  if (!basePath || basePath === ".") return normalizedName;
  return `${basePath.replace(/\/+$/, "")}/${normalizedName}`;
}

export function defaultPermissionMode(entry: SftpEntry) {
  if (entry.permissions_octal) {
    return entry.permissions_octal.replace(/^0+/, "") || "0";
  }

  const symbolic = entry.permissions || "";
  if (symbolic.length < 10) return entry.is_dir ? "755" : "644";
  const triplets = [symbolic.slice(1, 4), symbolic.slice(4, 7), symbolic.slice(7, 10)];
  const octal = triplets
    .map((segment) => {
      let value = 0;
      if (segment.includes("r")) value += 4;
      if (segment.includes("w")) value += 2;
      if (/[xsStT]/.test(segment)) value += 1;
      return String(value);
    })
    .join("");
  return octal || (entry.is_dir ? "755" : "644");
}

export function getVisibleSftpEntries({
  entries,
  searchQuery,
  showHidden,
}: {
  entries: SftpEntry[];
  searchQuery: string;
  showHidden: boolean;
}) {
  const query = searchQuery.trim().toLowerCase();
  return [...entries]
    .filter((entry) => (showHidden ? true : !entry.name.startsWith(".")))
    .filter((entry) => {
      if (!query) return true;
      return `${entry.name} ${entry.path} ${entry.permissions || ""}`.toLowerCase().includes(query);
    })
    .sort((left, right) => {
      if (left.is_dir !== right.is_dir) return left.is_dir ? -1 : 1;
      return left.name.localeCompare(right.name, undefined, { sensitivity: "base", numeric: true });
    });
}

export function getSftpBreadcrumbSegments(currentPath: string): SftpBreadcrumbSegment[] {
  if (!currentPath || currentPath === ".") {
    return [{ label: ".", path: "." }];
  }
  const absolute = currentPath.startsWith("/");
  const segments = currentPath.split("/").filter(Boolean);
  let cursor = absolute ? "" : "";
  return segments.map((segment, index) => {
    cursor = absolute
      ? `${cursor}/${segment}`.replace(/\/+/g, "/")
      : index === 0
        ? segment
        : `${cursor}/${segment}`;
    return {
      label: segment,
      path: cursor || "/",
    };
  });
}

export function createUploadTransfer(file: File, currentPath: string): TransferItem {
  return {
    id: nextTransferId(),
    direction: "upload",
    name: file.name,
    remotePath: `${currentPath.replace(/\/$/, "")}/${file.name}`,
    targetDir: currentPath,
    file,
    status: "queued",
    progress: 0,
    loaded: 0,
    total: file.size,
  };
}

export function createDownloadTransfer(entry: SftpEntry, currentPath: string): TransferItem {
  return {
    id: nextTransferId(),
    direction: "download",
    name: entry.name,
    remotePath: entry.path,
    targetDir: currentPath,
    status: "queued",
    progress: 0,
    loaded: 0,
    total: entry.size,
  };
}
