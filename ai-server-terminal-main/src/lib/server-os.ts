/**

 * Heuristic OS / distro detection for server list UI (no dedicated backend field yet).

 */



export type ServerOsKind =

  | "debian"

  | "ubuntu"

  | "centos"

  | "rhel"

  | "fedora"

  | "alpine"

  | "arch"

  | "opensuse"

  | "rocky"

  | "alma"

  | "oracle"

  | "amazon"

  | "windows"

  | "macos"

  | "freebsd"

  | "docker"

  | "kubernetes"

  | "unknown";



export const SERVER_OS_KINDS: ServerOsKind[] = [

  "debian",

  "ubuntu",

  "centos",

  "rhel",

  "fedora",

  "alpine",

  "arch",

  "opensuse",

  "rocky",

  "alma",

  "oracle",

  "amazon",

  "windows",

  "macos",

  "freebsd",

  "docker",

  "kubernetes",

  "unknown",

];



export interface ServerOsInput {

  server_type?: "ssh" | "rdp" | string;

  rdp?: boolean;

  name?: string;

  host?: string;

  username?: string;

  tags?: string;

  notes?: string;

  /** Backend SSH/RDP probe (preferred over heuristics). */

  detected_os?: string | null;

  detected_os_pretty?: string | null;

}



interface OsDetectionRule {

  kind: ServerOsKind;

  pattern: RegExp;

}



/** Ordered: more specific / infra hints before generic distro names. */

const OS_DETECTION_RULES: OsDetectionRule[] = [

  {

    kind: "kubernetes",

    pattern: /\b(kubernetes|k8s|k3s|microk8s|minikube|openshift|ocp|eks|aks|gke)\b/i,

  },

  {

    kind: "docker",

    pattern: /\b(docker|containerd|podman|docker-compose|compose|swarm)\b/i,

  },

  {

    kind: "macos",

    pattern: /\b(macos|mac-os|mac os x|mac os|darwin|osx|os x|apple silicon|m[12]\s+mac)\b/i,

  },

  { kind: "freebsd", pattern: /\b(freebsd|free-bsd)\b/i },

  {

    kind: "amazon",

    pattern: /\b(amazon[\s-]?linux|amzn2?|amzn-|aws[\s-]?linux)\b/i,

  },

  { kind: "ubuntu", pattern: /\bubuntu\b/i },

  { kind: "debian", pattern: /\bdebian\b/i },

  { kind: "rocky", pattern: /\b(rocky[\s-]?linux|rockylinux)\b/i },

  { kind: "alma", pattern: /\b(alma[\s-]?linux|almalinux)\b/i },

  { kind: "centos", pattern: /\bcentos\b/i },

  { kind: "rhel", pattern: /\b(rhel|red[\s-]?hat|redhat)\b/i },

  { kind: "fedora", pattern: /\bfedora\b/i },

  { kind: "alpine", pattern: /\balpine\b/i },

  {

    kind: "arch",

    pattern: /\b(arch[\s_-]?linux|archlinux|arch[\s/_-]?srv)\b/i,

  },

  { kind: "opensuse", pattern: /\b(opensuse|suse|sles|tumbleweed)\b/i },

  {

    kind: "oracle",

    pattern: /\b(oracle[\s-]?linux|oraclelinux|oel)\b/i,

  },

  {

    kind: "windows",

    pattern: /\b(windows|win32|win-server|winserver|mswin|hyper-v|winsrv|wsl)\b/i,

  },

];



function haystack(input: ServerOsInput): string {

  return [input.name, input.host, input.username, input.tags, input.notes].filter(Boolean).join(" ");

}



function isKnownOsKind(value: string): value is ServerOsKind {

  return (SERVER_OS_KINDS as readonly string[]).includes(value);

}



/** Prefer backend-detected OS; fall back to name/tags heuristics. */

export function resolveServerOs(input: ServerOsInput): ServerOsKind {

  const detected = (input.detected_os || "").trim().toLowerCase();

  if (detected && detected !== "unknown" && isKnownOsKind(detected)) {

    return detected;

  }

  return inferServerOs(input);

}



export function inferServerOs(input: ServerOsInput): ServerOsKind {

  if (input.server_type === "rdp" || input.rdp) return "windows";



  const text = haystack(input);



  for (const { kind, pattern } of OS_DETECTION_RULES) {

    if (pattern.test(text)) return kind;

  }



  return "unknown";

}



export function serverOsLabelKey(kind: ServerOsKind): string {

  return `srv.os.${kind}`;

}



const OS_DETECT_STALE_MS = 7 * 24 * 60 * 60 * 1000;



/** True when backend has no detection or it is older than 7 days. */

export function isOsDetectionStale(input: ServerOsInput & { detected_os_meta?: Record<string, unknown> }): boolean {

  if (!(input.detected_os || "").trim()) return true;

  const at = input.detected_os_meta?.detected_at;

  if (!at || typeof at !== "string") return true;

  const ts = Date.parse(at);

  if (Number.isNaN(ts)) return true;

  return Date.now() - ts >= OS_DETECT_STALE_MS;

}



export function formatLastConnected(iso: string | null | undefined, locale: string): string | null {

  if (!iso) return null;

  const date = new Date(iso);

  if (Number.isNaN(date.getTime())) return null;



  const diffSec = Math.round((date.getTime() - Date.now()) / 1000);

  const abs = Math.abs(diffSec);

  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });



  if (abs < 60) return rtf.format(diffSec, "second");

  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");

  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");

  if (abs < 86400 * 30) return rtf.format(Math.round(diffSec / 86400), "day");

  return date.toLocaleDateString(locale, { day: "numeric", month: "short" });

}


