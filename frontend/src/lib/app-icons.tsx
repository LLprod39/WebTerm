/**
 * WebTerm icon system — curated Lucide set for a premium ops product.
 *
 * Rules:
 * - One concept → one unique glyph (avoid reusing the same icon for different jobs)
 * - Structural / industrial preference over cute consumer glyphs
 * - Render with strokeWidth={1.5} and h-4 w-4 (or h-3.5 in dense UI)
 */
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Archive,
  ArrowLeftRight,
  BadgeCheck,
  BellDot,
  Blocks,
  BookMarked,
  BookOpen,
  Brain,
  Cable,
  CheckCircle2,
  ClipboardList,
  Clock3,
  Compass,
  Container,
  Copy,
  Download,
  Eye,
  FileCode2,
  FileSearch,
  FileText,
  Fingerprint,
  FolderOpen,
  FolderTree,
  Gauge,
  GitBranch,
  HardDrive,
  History,
  KeyRound,
  Layers3,
  LayoutGrid,
  Library,
  ListChecks,
  ListFilter,
  ListTree,
  Loader2,
  Lock,
  Mail,
  MessageSquareText,
  Network,
  NotebookPen,
  Package,
  Pause,
  Play,
  Plus,
  Radar,
  RefreshCw,
  RotateCcw,
  Save,
  Scale,
  ScrollText,
  Search,
  Send,
  ServerCog,
  Settings2,
  Share2,
  Shield,
  ShieldCheck,
  Sparkles,
  Square,
  SquarePen,
  Tag,
  Terminal,
  Trash2,
  Upload,
  UserCheck,
  UserRound,
  UsersRound,
  WandSparkles,
  Waypoints,
  Wrench,
  X,
  Zap,
} from "lucide-react";

/** Primary product navigation (sidebar). */
export const NavIcons = {
  dashboard: Gauge,
  servers: HardDrive,
  playbooks: ScrollText,
  agents: Radar,
  chat: MessageSquareText,
  studio: GitBranch,
  kubernetes: Container,
  mars: Compass,
  insights: Activity,
  plugins: Blocks,
  settings: Settings2,
} as const satisfies Record<string, LucideIcon>;

/** Settings IA — each item has its own glyph. */
export const SettingsIcons = {
  readiness: ClipboardList,
  ai: Sparkles,
  limits: Scale,
  notifications: BellDot,
  access: KeyRound,
  users: UserRound,
  groups: FolderTree,
  permissions: ShieldCheck,
  sso: Fingerprint,
  memory: BookMarked,
  audit: FileSearch,
  kubernetes: Container,
  plugins: Blocks,
  shell: Settings2,
  menu: ListTree,
} as const satisfies Record<string, LucideIcon>;

/** Studio top navigation. */
export const StudioNavIcons = {
  overview: LayoutGrid,
  drafts: WandSparkles,
  skills: Library,
  mcp: Cable,
  agents: Radar,
  runs: History,
  notifications: BellDot,
} as const satisfies Record<string, LucideIcon>;

/** Common CRUD / dialog actions. */
export const ActionIcons = {
  add: Plus,
  edit: SquarePen,
  delete: Trash2,
  save: Save,
  play: Play,
  pause: Pause,
  stop: Square,
  search: Search,
  refresh: RefreshCw,
  copy: Copy,
  send: Send,
  upload: Upload,
  download: Download,
  close: X,
  view: Eye,
  filter: ListFilter,
  loading: Loader2,
  share: Share2,
  lock: Lock,
  check: CheckCircle2,
  undo: RotateCcw,
} as const satisfies Record<string, LucideIcon>;

/** Server inventory dialogs & tabs. */
export const ServerIcons = {
  form: ServerCog,
  identity: HardDrive,
  auth: KeyRound,
  security: ShieldCheck,
  network: Network,
  group: Layers3,
  access: Share2,
  knowledge: NotebookPen,
  context: ScrollText,
  execute: Terminal,
  advanced: Wrench,
  os: BadgeCheck,
  transfer: ArrowLeftRight,
} as const satisfies Record<string, LucideIcon>;

/** Agent wizard, list, run. */
export const AgentIcons = {
  create: Radar,
  profile: ListChecks,
  template: Package,
  modeMini: Zap,
  modeFull: Brain,
  modeMulti: UsersRound,
  servers: HardDrive,
  schedule: Clock3,
  tools: Wrench,
  materials: FolderOpen,
  materialFile: FileText,
  materialCode: FileCode2,
  skills: BookOpen,
  sudo: Shield,
  run: Play,
  stop: Square,
  report: FileText,
  timeline: Activity,
  logs: Terminal,
  artifacts: Archive,
  events: ListFilter,
  health: Activity,
  worker: ServerCog,
  edit: SquarePen,
  delete: Trash2,
} as const satisfies Record<string, LucideIcon>;

/** Pipeline / studio graph nodes. */
export const PipelineNodeIcons = {
  agent: Radar,
  multiAgent: UsersRound,
  condition: GitBranch,
  email: Mail,
  humanApproval: UserCheck,
  ssh: Terminal,
  mcp: Cable,
  notify: BellDot,
  skill: Library,
  trigger: Zap,
  delay: Clock3,
  merge: Waypoints,
} as const satisfies Record<string, LucideIcon>;

/** Terminal chrome. */
export const TerminalIcons = {
  files: FolderOpen,
  workspace: LayoutGrid,
  ai: Sparkles,
  settings: Settings2,
  session: Terminal,
  connect: Plus,
} as const satisfies Record<string, LucideIcon>;

/** Knowledge / notes dialogs. */
export const KnowledgeIcons = {
  entry: NotebookPen,
  ai: Sparkles,
  category: Tag,
} as const satisfies Record<string, LucideIcon>;

/** Shared stroke class for premium minimal rendering. */
export const navIconClassName = "h-4 w-4 shrink-0 stroke-[1.5]";

export type { LucideIcon };
