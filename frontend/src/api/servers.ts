/**
 * src/api/servers.ts — Server management and Linux UI API.
 *
 * Migration target for functions from src/lib/api.ts related to:
 *   - Server CRUD (fetchServers, createServer, updateServer, deleteServer)
 *   - SFTP / file manager (sftpList, sftpRead, sftpWrite, sftpUpload, etc.)
 *   - Linux UI (fetchLinuxUiOverview, fetchLinuxUiServices, etc.)
 *   - Server memory (fetchMemoryOverview, purgeMemory, runDreams, etc.)
 *   - Server knowledge (fetchKnowledge, createKnowledge, etc.)
 *   - SSH host keys, shares, bulk operations
 *
 * Status: re-exported from src/api/index.ts (pending migration)
 */
export type {
  FrontendServer,
  ServerDetailsResponse,
  SftpEntry,
  SftpListResponse,
  LinuxUiCapabilities,
  LinuxUiOverview,
} from "@/lib/api";
