import { useEffect, useMemo, useRef, useState } from "react";
import yaml from "js-yaml";
import { Link } from "react-router-dom";
import {
  addServerGroupMember,
  
  clearMasterPassword,
  createServer,
  createServerGroup,
  createServerKnowledge,
  createServerShare,
  deleteServer,
  deleteServerGroup,
  deleteServerKnowledge,
  executeServerCommand,
  fetchFrontendBootstrap,
  fetchServerDetails,
  getGlobalServerContext,
  getGroupServerContext,
  getMasterPasswordStatus,
  listServerKnowledge,
  listServerShares,
  revealServerPassword,
  removeServerGroupMember,
  revokeServerShare,
  saveGlobalServerContext,
  saveGroupServerContext,
  setMasterPassword,
  subscribeServerGroup,
  testServer,
  updateServer,
  updateServerGroup,
  updateServerKnowledge,
  type FrontendServer,
  type ServerGroupRole,
} from "@/lib/api";
import { StatusIndicator } from "@/components/StatusIndicator";
import { useI18n } from "@/lib/i18n";
import {
  Terminal,
  Monitor,
  ChevronDown,
  ChevronRight,
  Plus,
  Search,
  Server,
  Settings,
  Trash2,
  Plug,
  Sparkles,
  Layers,
  Play,
  BookOpen,
  GripVertical,
  Copy,
  CheckCircle2,
  XCircle,
  Loader2,
  Save,
  FolderOpen,
  Upload,
  Download,
  FileJson,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogBody,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";

interface ServerForm {
  name: string;
  server_type: "ssh" | "rdp";
  host: string;
  port: number;
  username: string;
  auth_method: "password" | "key" | "key_password";
  key_path: string;
  password: string;
  tags: string;
  notes: string;
  group_id: number | null;
  is_active: boolean;
}

interface ShareItem {
  id: number;
  user_id: number;
  username: string;
  email: string;
  share_context: boolean;
  expires_at: string | null;
  created_at: string | null;
  is_active: boolean;
}

interface KnowledgeItem {
  id: number;
  title: string;
  content: string;
  category: string;
  category_label: string;
  updated_at: string | null;
  is_active: boolean;
}

type AdvancedTab = "access" | "knowledge" | "context" | "security" | "execute";
type MainTab = "servers" | "groups" | "playbook";

interface PlaybookTask {
  id: string;
  command: string;
  description: string;
  continueOnError: boolean;
}

interface Playbook {
  id: string;
  name: string;
  description: string;
  tasks: PlaybookTask[];
  createdAt: string;
}

interface PlaybookRunResult {
  serverId: number;
  serverName: string;
  taskResults: {
    taskId: string;
    command: string;
    status: "pending" | "running" | "success" | "error" | "skipped";
    output: string;
    exitCode?: number;
  }[];
}

function loadPlaybooks(): Playbook[] {
  try {
    const raw = localStorage.getItem("weu_playbooks");
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function savePlaybooks(playbooks: Playbook[]) {
  localStorage.setItem("weu_playbooks", JSON.stringify(playbooks));
}

function newTaskId() {
  return `t_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

function newPlaybookId() {
  return `pb_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

/** Parse Ansible playbook (YAML or JSON) into our Playbook format */
function parseAnsiblePlaybook(content: string, filename: string): Playbook {
  // Try YAML first, then JSON
  let parsed: unknown;
  try {
    parsed = yaml.load(content);
  } catch {
    parsed = JSON.parse(content);
  }

  const tasks: PlaybookTask[] = [];
  let playbookName = filename.replace(/\.(ya?ml|json)$/i, "");
  let playbookDesc = "";

  // Ansible playbooks are arrays of plays
  const plays = Array.isArray(parsed) ? parsed : [parsed];

  for (const play of plays) {
    if (!play || typeof play !== "object") continue;
    const p = play as Record<string, unknown>;

    if (p.name && typeof p.name === "string" && !playbookDesc) {
      playbookName = p.name;
    }
    if (p.hosts && typeof p.hosts === "string") {
      playbookDesc = `hosts: ${p.hosts}`;
    }

    // Extract tasks from "tasks", "pre_tasks", "post_tasks", "handlers"
    for (const section of ["pre_tasks", "tasks", "post_tasks", "handlers"]) {
      const sectionTasks = (p as Record<string, unknown>)[section];
      if (!Array.isArray(sectionTasks)) continue;

      for (const task of sectionTasks) {
        if (!task || typeof task !== "object") continue;
        const t = task as Record<string, unknown>;
        const taskName = (t.name as string) || "";
        let command = "";
        let continueOnError = Boolean(t.ignore_errors);

        // Extract command from common Ansible modules
        if (typeof t.shell === "string") {
          command = t.shell;
        } else if (typeof t.command === "string") {
          command = t.command;
        } else if (typeof t.raw === "string") {
          command = t.raw;
        } else if (typeof t.script === "string") {
          command = t.script;
        } else if (t.shell && typeof t.shell === "object") {
          command = (t.shell as Record<string, unknown>).cmd as string || "";
        } else if (t.command && typeof t.command === "object") {
          command = (t.command as Record<string, unknown>).cmd as string || "";
        } else if (typeof t.apt === "object" || typeof t.apt === "string") {
          const apt = typeof t.apt === "string" ? { name: t.apt } : t.apt as Record<string, unknown>;
          const pkg = apt.name || apt.pkg || "";
          const state = apt.state || "present";
          command = `apt-get ${state === "absent" ? "remove" : "install"} -y ${pkg}`;
        } else if (typeof t.yum === "object" || typeof t.yum === "string") {
          const yum = typeof t.yum === "string" ? { name: t.yum } : t.yum as Record<string, unknown>;
          const pkg = yum.name || "";
          const state = yum.state || "present";
          command = `yum ${state === "absent" ? "remove" : "install"} -y ${pkg}`;
        } else if (typeof t.systemd === "object" || typeof t.service === "object") {
          const svc = (t.systemd || t.service) as Record<string, unknown>;
          const name = svc.name || "";
          const state = svc.state || "started";
          const stateMap: Record<string, string> = { started: "start", stopped: "stop", restarted: "restart", reloaded: "reload" };
          command = `systemctl ${stateMap[state as string] || state} ${name}`;
          if (svc.enabled === true) command += ` && systemctl enable ${name}`;
        } else if (typeof t.copy === "object") {
          const cp = t.copy as Record<string, unknown>;
          if (cp.content && cp.dest) {
            const escaped = String(cp.content).replace(/'/g, "'\\''");
            command = `echo '${escaped}' > ${cp.dest}`;
          } else if (cp.src && cp.dest) {
            command = `cp ${cp.src} ${cp.dest}`;
          }
        } else if (typeof t.file === "object") {
          const f = t.file as Record<string, unknown>;
          if (f.state === "directory") command = `mkdir -p ${f.path || f.dest || ""}`;
          else if (f.state === "absent") command = `rm -rf ${f.path || f.dest || ""}`;
          else if (f.mode) command = `chmod ${f.mode} ${f.path || f.dest || ""}`;
        } else if (typeof t.lineinfile === "object") {
          const l = t.lineinfile as Record<string, unknown>;
          command = `# lineinfile: ${l.path || l.dest || ""} line="${l.line || ""}"`;
        } else if (typeof t.template === "object") {
          const tmpl = t.template as Record<string, unknown>;
          command = `# template: ${tmpl.src} -> ${tmpl.dest}`;
        } else if (typeof t.git === "object") {
          const g = t.git as Record<string, unknown>;
          command = `git clone ${g.repo || ""} ${g.dest || ""}${g.version ? ` -b ${g.version}` : ""}`;
        } else if (typeof t.pip === "object") {
          const pip = t.pip as Record<string, unknown>;
          command = `pip install ${pip.name || ""}${pip.requirements ? ` -r ${pip.requirements}` : ""}`;
        } else if (typeof t.docker_container === "object") {
          const dc = t.docker_container as Record<string, unknown>;
          command = `# docker: ${dc.name} image=${dc.image || ""} state=${dc.state || "started"}`;
        } else {
          // Unknown module — show as comment with module name
          const moduleKeys = Object.keys(t).filter((k) => !["name", "when", "register", "become", "become_user", "tags", "notify", "ignore_errors", "changed_when", "failed_when", "loop", "with_items", "vars", "environment", "no_log", "delegate_to", "run_once", "block", "rescue", "always"].includes(k));
          if (moduleKeys.length > 0) {
            const mod = moduleKeys[0];
            const val = t[mod];
            command = `# ansible.${mod}: ${typeof val === "string" ? val : JSON.stringify(val)}`;
          }
        }

        if (command || taskName) {
          tasks.push({
            id: newTaskId(),
            command: command || `# ${taskName}`,
            description: taskName,
            continueOnError,
          });
        }
      }
    }
  }

  if (tasks.length === 0) {
    throw new Error("No tasks found in playbook. Ensure it contains tasks with shell/command/apt/systemd modules.");
  }

  return {
    id: newPlaybookId(),
    name: playbookName,
    description: playbookDesc,
    tasks,
    createdAt: new Date().toISOString(),
  };
}

/** Export playbook to JSON */
function exportPlaybookAsJson(pb: Playbook) {
  const ansible = [{
    name: pb.name,
    hosts: "all",
    become: true,
    tasks: pb.tasks.map((t) => {
      const task: Record<string, unknown> = { name: t.description || t.command };
      if (t.command.startsWith("#")) {
        task.debug = { msg: t.command };
      } else {
        task.shell = t.command;
      }
      if (t.continueOnError) task.ignore_errors = true;
      return task;
    }),
  }];
  const blob = new Blob([JSON.stringify(ansible, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${pb.name.replace(/\s+/g, "_").toLowerCase()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function initialForm(): ServerForm {
  return {
    name: "",
    server_type: "ssh",
    host: "",
    port: 22,
    username: "root",
    auth_method: "password",
    key_path: "",
    password: "",
    tags: "",
    notes: "",
    group_id: null,
    is_active: true,
  };
}

function asPayload(form: ServerForm) {
  return {
    name: form.name,
    server_type: form.server_type,
    host: form.host,
    port: form.port,
    username: form.username,
    auth_method: form.auth_method,
    key_path: form.key_path,
    password: form.password,
    tags: form.tags,
    notes: form.notes,
    group_id: form.group_id,
    is_active: form.is_active,
  };
}

function toJson(text: string): Record<string, string> {
  const trimmed = text.trim();
  if (!trimmed) return {};
  return JSON.parse(trimmed) as Record<string, string>;
}

function formatCommandOutput(output: unknown): string {
  if (typeof output === "string") return output;
  if (!output || typeof output !== "object") return "(no output)";

  const value = output as Record<string, unknown>;
  const stdout = typeof value.stdout === "string" ? value.stdout : "";
  const stderr = typeof value.stderr === "string" ? value.stderr : "";
  const exitCode = value.exit_code;

  if (stdout || stderr || exitCode !== undefined) {
    const parts: string[] = [];
    if (stdout) parts.push(`STDOUT:\n${stdout}`);
    if (stderr) parts.push(`STDERR:\n${stderr}`);
    if (exitCode !== undefined) parts.push(`EXIT CODE: ${String(exitCode)}`);
    return parts.join("\n\n");
  }

  try {
    return JSON.stringify(output, null, 2);
  } catch {
    return String(output);
  }
}

export default function Servers() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [advancedTab, setAdvancedTab] = useState<AdvancedTab>("access");
  const [mainTab, setMainTab] = useState<MainTab>("servers");
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [selectedServerId, setSelectedServerId] = useState<number | null>(null);
  const [groupName, setGroupName] = useState("");
  const [groupDescription, setGroupDescription] = useState("");
  const [groupColor, setGroupColor] = useState("#3b82f6");
  const [groupSaving, setGroupSaving] = useState(false);
  // Playbook state
  const [playbooks, setPlaybooks] = useState<Playbook[]>(loadPlaybooks);
  const [activePlaybook, setActivePlaybook] = useState<Playbook | null>(null);
  const [playbookName, setPlaybookName] = useState("");
  const [playbookDesc, setPlaybookDesc] = useState("");
  const [playbookTasks, setPlaybookTasks] = useState<PlaybookTask[]>([]);
  const [playbookTargets, setPlaybookTargets] = useState<Set<number>>(new Set());
  const [playbookRunning, setPlaybookRunning] = useState(false);
  const [playbookResults, setPlaybookResults] = useState<PlaybookRunResult[]>([]);
  const [playbookView, setPlaybookView] = useState<"list" | "edit" | "run">("list");

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingServer, setEditingServer] = useState<FrontendServer | null>(null);
  const [form, setForm] = useState<ServerForm>(initialForm());
  const [saving, setSaving] = useState(false);

  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [advancedServer, setAdvancedServer] = useState<FrontendServer | null>(null);
  const [advancedLoading, setAdvancedLoading] = useState(false);

  const [shares, setShares] = useState<ShareItem[]>([]);
  const [shareUser, setShareUser] = useState("");
  const [shareContext, setShareContext] = useState(true);
  const [shareExpiresAt, setShareExpiresAt] = useState("");

  const [knowledge, setKnowledge] = useState<KnowledgeItem[]>([]);
  const [knowledgeTitle, setKnowledgeTitle] = useState("");
  const [knowledgeContent, setKnowledgeContent] = useState("");
  const [knowledgeCategory, setKnowledgeCategory] = useState("other");
  const [knowledgeEditingId, setKnowledgeEditingId] = useState<number | null>(null);

  const [globalRules, setGlobalRules] = useState("");
  const [globalForbidden, setGlobalForbidden] = useState("");
  const [globalRequired, setGlobalRequired] = useState("");
  const [globalEnvJson, setGlobalEnvJson] = useState("{}");

  const [groupRules, setGroupRules] = useState("");
  const [groupForbidden, setGroupForbidden] = useState("");
  const [groupEnvJson, setGroupEnvJson] = useState("{}");
  const [groupMemberUser, setGroupMemberUser] = useState("");
  const [groupMemberRole, setGroupMemberRole] = useState<ServerGroupRole>("member");
  const [groupRemoveUserId, setGroupRemoveUserId] = useState("");

  const [masterPassword, setMasterPasswordText] = useState("");
  const [hasMasterPassword, setHasMasterPassword] = useState(false);
  const [revealedPassword, setRevealedPassword] = useState("");

  const [execCommand, setExecCommand] = useState("hostname");
  const [execResult, setExecResult] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["frontend", "bootstrap"],
    queryFn: fetchFrontendBootstrap,
    staleTime: 20_000,
  });

  const servers = data?.servers || [];
  const groups = data?.groups || [];
  const onlineCount = servers.filter((server) => server.status === "online").length;
  const sharedCount = servers.filter((server) => server.is_shared).length;
  const groupCount = groups.filter((group) => group.id !== null).length;

  const filtered = useMemo(() => {
    if (!search) return servers;
    const q = search.toLowerCase();
    return servers.filter((s) => s.name.toLowerCase().includes(q) || s.host.includes(q));
  }, [servers, search]);

  const grouped = useMemo(() => {
    const map: Record<string, typeof filtered> = {};
    filtered.forEach((s) => {
      (map[s.group_name] ??= []).push(s);
    });
    return map;
  }, [filtered]);

  const toggleGroup = (g: string) => setCollapsed((c) => ({ ...c, [g]: !c[g] }));

  useEffect(() => {
    if (!filtered.length) {
      setSelectedServerId(null);
      return;
    }
    if (!selectedServerId || !filtered.some((server) => server.id === selectedServerId)) {
      setSelectedServerId(filtered[0].id);
    }
  }, [filtered, selectedServerId]);

  const selectedServer =
    filtered.find((server) => server.id === selectedServerId) ||
    servers.find((server) => server.id === selectedServerId) ||
    null;

  const reload = async () => {
    await queryClient.invalidateQueries({ queryKey: ["frontend", "bootstrap"] });
    await queryClient.invalidateQueries({ queryKey: ["settings", "activity"] });
  };

  const openCreate = () => {
    setEditingServer(null);
    setForm(initialForm());
    setDialogOpen(true);
  };

  const openEdit = async (server: FrontendServer) => {
    setEditingServer(server);
    const details = await fetchServerDetails(server.id);
    setForm({
      name: details.name,
      server_type: details.server_type,
      host: details.host,
      port: details.port,
      username: details.username,
      auth_method: details.auth_method,
      key_path: details.key_path || "",
      password: "",
      tags: details.tags || "",
      notes: details.notes || "",
      group_id: details.group_id,
      is_active: details.is_active,
    });
    setDialogOpen(true);
  };

  const onSave = async () => {
    setSaving(true);
    try {
      if (editingServer) await updateServer(editingServer.id, asPayload(form));
      else await createServer(asPayload(form));
      setDialogOpen(false);
      await reload();
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (server: FrontendServer) => {
    if (!confirm(`Delete server ${server.name}?`)) return;
    await deleteServer(server.id);
    await reload();
  };

  const onTest = async (server: FrontendServer) => {
    const result = await testServer(server.id, {});
    if (result.success) alert(`Connection successful for ${server.name}`);
    else alert(`Connection failed: ${result.error || "unknown error"}`);
    await reload();
  };

  const onCreateGroup = async () => {
    if (!groupName.trim()) return;
    setGroupSaving(true);
    try {
      await createServerGroup({
        name: groupName.trim(),
        description: groupDescription.trim(),
        color: groupColor,
      });
      setGroupName("");
      setGroupDescription("");
      setGroupColor("#3b82f6");
      await reload();
    } finally {
      setGroupSaving(false);
    }
  };

  const onRenameGroup = async (groupId: number, name: string) => {
    const next = prompt("New group name", name);
    if (!next || next.trim() === name) return;
    await updateServerGroup(groupId, { name: next.trim() });
    await reload();
  };

  const onDeleteGroup = async (groupId: number, name: string) => {
    if (!confirm(`Delete group ${name}?`)) return;
    await deleteServerGroup(groupId);
    await reload();
  };

  // Playbook helpers
  const addPlaybookTask = () => {
    setPlaybookTasks((prev) => [...prev, { id: newTaskId(), command: "", description: "", continueOnError: false }]);
  };

  const updatePlaybookTask = (id: string, patch: Partial<PlaybookTask>) => {
    setPlaybookTasks((prev) => prev.map((t) => (t.id === id ? { ...t, ...patch } : t)));
  };

  const removePlaybookTask = (id: string) => {
    setPlaybookTasks((prev) => prev.filter((t) => t.id !== id));
  };

  const moveTask = (idx: number, dir: -1 | 1) => {
    setPlaybookTasks((prev) => {
      const next = [...prev];
      const target = idx + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[idx], next[target]] = [next[target], next[idx]];
      return next;
    });
  };

  const toggleTarget = (id: number) => {
    setPlaybookTargets((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllTargets = () => {
    setPlaybookTargets(new Set(servers.filter((s) => s.status === "online").map((s) => s.id)));
  };

  const clearTargets = () => setPlaybookTargets(new Set());

  const openNewPlaybook = () => {
    setActivePlaybook(null);
    setPlaybookName("");
    setPlaybookDesc("");
    setPlaybookTasks([{ id: newTaskId(), command: "", description: "", continueOnError: false }]);
    setPlaybookTargets(new Set());
    setPlaybookResults([]);
    setPlaybookView("edit");
  };

  const openEditPlaybook = (pb: Playbook) => {
    setActivePlaybook(pb);
    setPlaybookName(pb.name);
    setPlaybookDesc(pb.description);
    setPlaybookTasks([...pb.tasks]);
    setPlaybookTargets(new Set());
    setPlaybookResults([]);
    setPlaybookView("edit");
  };

  const onSavePlaybook = () => {
    if (!playbookName.trim() || playbookTasks.length === 0) return;
    const pb: Playbook = {
      id: activePlaybook?.id || newPlaybookId(),
      name: playbookName.trim(),
      description: playbookDesc.trim(),
      tasks: playbookTasks.filter((t) => t.command.trim()),
      createdAt: activePlaybook?.createdAt || new Date().toISOString(),
    };
    const updated = activePlaybook
      ? playbooks.map((p) => (p.id === activePlaybook.id ? pb : p))
      : [...playbooks, pb];
    setPlaybooks(updated);
    savePlaybooks(updated);
    setActivePlaybook(pb);
  };

  const onDeletePlaybook = (id: string) => {
    if (!confirm("Delete this playbook?")) return;
    const updated = playbooks.filter((p) => p.id !== id);
    setPlaybooks(updated);
    savePlaybooks(updated);
    if (activePlaybook?.id === id) setPlaybookView("list");
  };

  const onDuplicatePlaybook = (pb: Playbook) => {
    const dup: Playbook = {
      ...pb,
      id: newPlaybookId(),
      name: `${pb.name} (copy)`,
      createdAt: new Date().toISOString(),
      tasks: pb.tasks.map((t) => ({ ...t, id: newTaskId() })),
    };
    const updated = [...playbooks, dup];
    setPlaybooks(updated);
    savePlaybooks(updated);
  };

  const fileInputRef = useRef<HTMLInputElement>(null);

  const onImportFile = async (file: File) => {
    try {
      const text = await file.text();
      const pb = parseAnsiblePlaybook(text, file.name);
      const updated = [...playbooks, pb];
      setPlaybooks(updated);
      savePlaybooks(updated);
      setActivePlaybook(pb);
      setPlaybookName(pb.name);
      setPlaybookDesc(pb.description);
      setPlaybookTasks([...pb.tasks]);
      setPlaybookTargets(new Set());
      setPlaybookResults([]);
      setPlaybookView("edit");
    } catch (err) {
      alert(`Failed to parse playbook: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const onFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onImportFile(file);
    e.target.value = "";
  };

  const onDropPlaybook = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) onImportFile(file);
  };

  const onRunPlaybook = async () => {
    const validTasks = playbookTasks.filter((t) => t.command.trim());
    const targetIds = Array.from(playbookTargets);
    if (!validTasks.length || !targetIds.length) return;

    setPlaybookRunning(true);
    setPlaybookView("run");

    const results: PlaybookRunResult[] = targetIds.map((sid) => {
      const srv = servers.find((s) => s.id === sid);
      return {
        serverId: sid,
        serverName: srv?.name || `Server #${sid}`,
        taskResults: validTasks.map((t) => ({
          taskId: t.id,
          command: t.command,
          status: "pending" as const,
          output: "",
        })),
      };
    });
    setPlaybookResults([...results]);

    for (let si = 0; si < results.length; si++) {
      const sr = results[si];
      let shouldSkip = false;
      for (let ti = 0; ti < validTasks.length; ti++) {
        const task = validTasks[ti];
        if (shouldSkip) {
          sr.taskResults[ti].status = "skipped";
          sr.taskResults[ti].output = "Skipped due to previous error";
          setPlaybookResults([...results]);
          continue;
        }

        sr.taskResults[ti].status = "running";
        setPlaybookResults([...results]);

        try {
          const resp = await executeServerCommand(sr.serverId, task.command, "");
          if (resp.success) {
            sr.taskResults[ti].status = "success";
            sr.taskResults[ti].output = formatCommandOutput(resp.output);
            sr.taskResults[ti].exitCode = 0;
          } else {
            sr.taskResults[ti].status = "error";
            sr.taskResults[ti].output = resp.error || "Command failed";
            sr.taskResults[ti].exitCode = 1;
            if (!task.continueOnError) shouldSkip = true;
          }
        } catch (err) {
          sr.taskResults[ti].status = "error";
          sr.taskResults[ti].output = String(err);
          sr.taskResults[ti].exitCode = 1;
          if (!task.continueOnError) shouldSkip = true;
        }
        setPlaybookResults([...results]);
      }
    }

    setPlaybookRunning(false);
  };

  const openAdvanced = async (server: FrontendServer) => {
    setAdvancedServer(server);
    setAdvancedOpen(true);
    setAdvancedLoading(true);
    setAdvancedTab("access");
    setExecResult("");
    setRevealedPassword("");
    setKnowledgeEditingId(null);
    setGroupMemberUser("");
    setGroupRemoveUserId("");
    try {
      const [sharesResp, knowledgeResp, globalCtx, masterStatus] = await Promise.all([
        listServerShares(server.id).catch(() => ({ success: false, shares: [] })),
        listServerKnowledge(server.id).catch(() => ({ success: false, items: [], categories: [] })),
        getGlobalServerContext().catch(() => null),
        getMasterPasswordStatus().catch(() => ({ has_master_password: false })),
      ]);
      setShares(sharesResp.success ? sharesResp.shares : []);
      setKnowledge((knowledgeResp.items || []) as KnowledgeItem[]);
      setHasMasterPassword(Boolean(masterStatus.has_master_password));

      if (globalCtx) {
        setGlobalRules(globalCtx.rules || "");
        setGlobalForbidden((globalCtx.forbidden_commands || []).join("\n"));
        setGlobalRequired((globalCtx.required_checks || []).join("\n"));
        setGlobalEnvJson(JSON.stringify(globalCtx.environment_vars || {}, null, 2));
      }

      if (server.group_id) {
        const groupCtx = await getGroupServerContext(server.group_id).catch(() => null);
        if (groupCtx) {
          setGroupRules(groupCtx.rules || "");
          setGroupForbidden((groupCtx.forbidden_commands || []).join("\n"));
          setGroupEnvJson(JSON.stringify(groupCtx.environment_vars || {}, null, 2));
        }
      } else {
        setGroupRules("");
        setGroupForbidden("");
        setGroupEnvJson("{}");
      }
    } finally {
      setAdvancedLoading(false);
    }
  };

  const refreshShares = async () => {
    if (!advancedServer) return;
    const resp = await listServerShares(advancedServer.id);
    setShares(resp.shares || []);
  };

  const refreshKnowledge = async () => {
    if (!advancedServer) return;
    const resp = await listServerKnowledge(advancedServer.id);
    setKnowledge((resp.items || []) as KnowledgeItem[]);
  };

  const onShareCreate = async () => {
    if (!advancedServer || !shareUser.trim()) return;
    await createServerShare(advancedServer.id, {
      user: shareUser.trim(),
      share_context: shareContext,
      expires_at: shareExpiresAt ? new Date(shareExpiresAt).toISOString() : null,
    });
    setShareUser("");
    setShareExpiresAt("");
    await refreshShares();
  };

  const onShareRevoke = async (shareId: number) => {
    if (!advancedServer) return;
    await revokeServerShare(advancedServer.id, shareId);
    await refreshShares();
  };

  const onKnowledgeCreate = async () => {
    if (!advancedServer || !knowledgeTitle.trim() || !knowledgeContent.trim()) return;
    await createServerKnowledge(advancedServer.id, {
      title: knowledgeTitle.trim(),
      content: knowledgeContent.trim(),
      category: knowledgeCategory,
      is_active: true,
    });
    setKnowledgeTitle("");
    setKnowledgeContent("");
    await refreshKnowledge();
  };

  const onKnowledgeDelete = async (id: number) => {
    if (!advancedServer) return;
    await deleteServerKnowledge(advancedServer.id, id);
    if (knowledgeEditingId === id) setKnowledgeEditingId(null);
    await refreshKnowledge();
  };

  const onKnowledgeEdit = async (item: KnowledgeItem) => {
    if (!advancedServer) return;
    const title = prompt("Knowledge title", item.title);
    if (!title) {
      setKnowledgeEditingId(null);
      return;
    }
    const content = prompt("Knowledge content", item.content);
    if (!content) {
      setKnowledgeEditingId(null);
      return;
    }
    await updateServerKnowledge(advancedServer.id, item.id, {
      title: title.trim(),
      content: content.trim(),
      category: item.category,
      is_active: item.is_active,
    });
    setKnowledgeEditingId(null);
    await refreshKnowledge();
  };

  const onKnowledgeToggle = async (item: KnowledgeItem) => {
    if (!advancedServer) return;
    await updateServerKnowledge(advancedServer.id, item.id, { is_active: !item.is_active });
    await refreshKnowledge();
  };

  const onSaveGlobalContext = async () => {
    let env: Record<string, string>;
    try {
      env = toJson(globalEnvJson);
    } catch {
      alert("Invalid Global context JSON");
      return;
    }
    await saveGlobalServerContext({
      rules: globalRules,
      forbidden_commands: globalForbidden,
      required_checks: globalRequired,
      environment_vars: env,
    });
    alert("Global context saved");
  };

  const onSaveGroupContext = async () => {
    if (!advancedServer?.group_id) return;
    let env: Record<string, string>;
    try {
      env = toJson(groupEnvJson);
    } catch {
      alert("Invalid Group context JSON");
      return;
    }
    await saveGroupServerContext(advancedServer.group_id, {
      rules: groupRules,
      forbidden_commands: groupForbidden,
      environment_vars: env,
    });
    alert("Group context saved");
  };

  const onAddGroupMember = async () => {
    if (!advancedServer?.group_id || !groupMemberUser.trim()) return;
    await addServerGroupMember(advancedServer.group_id, { user: groupMemberUser.trim(), role: groupMemberRole });
    setGroupMemberUser("");
    alert("Group member updated");
  };

  const onRemoveGroupMember = async () => {
    if (!advancedServer?.group_id || !groupRemoveUserId.trim()) return;
    const userId = Number(groupRemoveUserId);
    if (!Number.isFinite(userId) || userId <= 0) {
      alert("Invalid user id");
      return;
    }
    await removeServerGroupMember(advancedServer.group_id, userId);
    setGroupRemoveUserId("");
    alert("Group member removed");
  };

  const onSetMasterPassword = async () => {
    if (!masterPassword.trim()) return;
    await setMasterPassword(masterPassword.trim());
    setHasMasterPassword(true);
    alert("Master password stored in session");
  };

  const onClearMasterPassword = async () => {
    await clearMasterPassword();
    setHasMasterPassword(false);
    alert("Master password cleared from session");
  };

  const onRevealPassword = async () => {
    if (!advancedServer) return;
    const resp = await revealServerPassword(advancedServer.id, masterPassword.trim());
    if (resp.success) setRevealedPassword(resp.password || "");
    else alert(resp.error || "Failed to reveal password");
  };

  const onExecuteCommand = async () => {
    if (!advancedServer || !execCommand.trim()) return;
    const resp = await executeServerCommand(advancedServer.id, execCommand, "");
    if (resp.success) setExecResult(formatCommandOutput(resp.output));
    else setExecResult(`ERROR: ${resp.error || "Unknown error"}`);
  };

  if (isLoading) return <div className="p-6 text-sm text-muted-foreground">{t("srv.loading")}</div>;
  if (error || !data) return <div className="p-6 text-sm text-destructive">{t("srv.error")}</div>;

  return (
    <div className="p-5 max-w-6xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
        <div>
          <h1 className="text-lg font-semibold text-foreground">{t("srv.title")}</h1>
          <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
            <span>{servers.length} total</span>
            <span className="text-border">·</span>
            <span className="text-emerald-400">{onlineCount} online</span>
            {sharedCount > 0 && (
              <>
                <span className="text-border">·</span>
                <span>{sharedCount} shared</span>
              </>
            )}
            <span className="text-border">·</span>
            <span>{groupCount} groups</span>
          </div>
        </div>
        <div className="flex gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder={t("srv.search")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-8 w-48 bg-card border-border text-xs"
            />
          </div>
          <Button size="sm" className="gap-1.5 h-8 text-xs" onClick={openCreate}>
            <Plus className="h-3.5 w-3.5" /> {t("srv.add")}
          </Button>
        </div>
      </div>

      <Tabs value={mainTab} onValueChange={(v) => setMainTab(v as MainTab)} className="space-y-3">
        <TabsList className="w-full justify-start">
          <TabsTrigger value="servers" className="gap-2">
            <Server className="h-4 w-4" /> {t("srv.list")}
          </TabsTrigger>
          <TabsTrigger value="groups" className="gap-2">
            <Layers className="h-4 w-4" /> {t("srv.groups")}
          </TabsTrigger>
          <TabsTrigger value="playbook" className="gap-2">
            <BookOpen className="h-4 w-4" /> Playbook
          </TabsTrigger>
        </TabsList>

        <TabsContent value="servers" className="space-y-3">
          {Object.entries(grouped).map(([group, inGroup]) => {
            const isCollapsed = collapsed[group];
            return (
              <div key={group} className="bg-card border border-border rounded-lg overflow-hidden">
                <button
                  onClick={() => toggleGroup(group)}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-secondary/50 transition-colors text-left"
                  aria-label={`Toggle ${group} group`}
                >
                  {isCollapsed ? <ChevronRight className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
                  <Server className="h-4 w-4 text-primary" />
                  <span className="font-medium text-foreground">{group}</span>
                  <span className="text-xs text-muted-foreground ml-auto">{inGroup.length} {t("srv.servers_count")}</span>
                </button>

                <AnimatePresence initial={false}>
                  {!isCollapsed && (
                    <motion.div
                      initial={{ height: 0 }}
                      animate={{ height: "auto" }}
                      exit={{ height: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="border-t border-border">
                        {inGroup.map((server, i) => (
                          <div
                            key={server.id}
                            className={`flex items-center gap-4 px-4 py-3 hover:bg-secondary/30 transition-colors ${
                              i < inGroup.length - 1 ? "border-b border-border/50" : ""
                            }`}
                          >
                            <StatusIndicator status={server.status} showLabel={false} />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-foreground truncate">{server.name}</p>
                              <p className="text-xs text-muted-foreground font-mono">
                                {server.host}:{server.port}
                              </p>
                            </div>
                            <StatusIndicator status={server.status} />
                            <div className="flex gap-1.5 shrink-0">
                              <Link to={`/servers/${server.id}/terminal`}>
                                <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7 border-border hover:border-primary hover:text-primary">
                                  <Terminal className="h-3 w-3" /> SSH
                                </Button>
                              </Link>
                              {server.rdp && (
                                <Link to={`/servers/${server.id}/rdp`}>
                                  <Button size="sm" variant="outline" className="gap-1.5 text-xs h-7 border-border hover:border-info hover:text-info">
                                    <Monitor className="h-3 w-3" /> RDP
                                  </Button>
                                </Link>
                              )}
                              <Button size="sm" variant="outline" className="h-7 px-2" onClick={() => openAdvanced(server)}>
                                <Sparkles className="h-3.5 w-3.5" />
                              </Button>
                              {server.can_edit && (
                                <>
                                  <Button size="sm" variant="outline" className="h-7 px-2" onClick={() => openEdit(server)}>
                                    <Settings className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button size="sm" variant="destructive" className="h-7 px-2" onClick={() => onDelete(server)}>
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>
                                </>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </TabsContent>

        <TabsContent value="groups" className="space-y-3">
          <section className="bg-card border border-border rounded-lg p-4 space-y-3">
            <h2 className="text-sm font-medium">{t("srv.groups")}</h2>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
              <Input placeholder={t("srv.group_name")} value={groupName} onChange={(e) => setGroupName(e.target.value)} />
              <Input
                placeholder={t("srv.description")}
                value={groupDescription}
                onChange={(e) => setGroupDescription(e.target.value)}
              />
              <Input type="color" value={groupColor} onChange={(e) => setGroupColor(e.target.value)} />
              <Button onClick={onCreateGroup} disabled={!groupName.trim() || groupSaving}>
                {groupSaving ? "..." : t("srv.create_group")}
              </Button>
            </div>
            <div className="space-y-2">
              {groups
                .filter((g) => g.id !== null)
                .map((g) => (
                  <div key={g.id!} className="flex items-center gap-2 border border-border rounded px-3 py-2">
                    <div className="text-sm">
                      {g.name}
                      <span className="text-xs text-muted-foreground ml-2">{g.server_count} servers</span>
                    </div>
                    <div className="ml-auto flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => subscribeServerGroup(g.id!, "follow")}>
                        Follow
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => subscribeServerGroup(g.id!, "favorite")}>
                        Favorite
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => onRenameGroup(g.id!, g.name)}>
                        Rename
                      </Button>
                      <Button size="sm" variant="destructive" onClick={() => onDeleteGroup(g.id!, g.name)}>
                        Delete
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
          </section>
        </TabsContent>

        <TabsContent value="playbook" className="space-y-3">
          {/* Hidden file input */}
          <input ref={fileInputRef} type="file" accept=".yml,.yaml,.json" className="hidden" onChange={onFileInputChange} />

          {/* PLAYBOOK LIST */}
          {playbookView === "list" && (
            <section className="bg-card border border-border rounded-lg p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-foreground">Playbooks</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">Import Ansible playbooks (YAML/JSON) or create from scratch</p>
                </div>
                <div className="flex gap-1.5">
                  <Button size="sm" variant="outline" className="gap-1.5 h-8 text-xs" onClick={() => fileInputRef.current?.click()}>
                    <Upload className="h-3.5 w-3.5" /> Import
                  </Button>
                  <Button size="sm" className="gap-1.5 h-8 text-xs" onClick={openNewPlaybook}>
                    <Plus className="h-3.5 w-3.5" /> New Playbook
                  </Button>
                </div>
              </div>

              {/* Drag & drop zone */}
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={onDropPlaybook}
                className="border-2 border-dashed border-border rounded-lg p-6 text-center transition-colors hover:border-primary/40 hover:bg-primary/5 cursor-pointer"
                onClick={() => fileInputRef.current?.click()}
              >
                <FileJson className="h-8 w-8 mx-auto mb-2 text-muted-foreground/40" />
                <p className="text-xs text-muted-foreground">
                  Drop Ansible playbook here (.yml, .yaml, .json) or <span className="text-primary underline">browse</span>
                </p>
                <p className="text-[10px] text-muted-foreground/60 mt-1">
                  Supports: shell, command, apt, yum, systemd, service, copy, file, git, pip and more
                </p>
              </div>

              {playbooks.length === 0 ? (
                <div className="text-center py-6 text-muted-foreground">
                  <p className="text-sm">No playbooks yet</p>
                  <p className="text-xs mt-1">Import an Ansible playbook or create a new one</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {playbooks.map((pb) => (
                    <div key={pb.id} className="flex items-center gap-4 px-4 py-3 rounded-lg border border-border bg-secondary/10 hover:bg-secondary/30 transition-colors">
                      <BookOpen className="h-4 w-4 text-primary shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{pb.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {pb.tasks.length} task{pb.tasks.length !== 1 ? "s" : ""} · {new Date(pb.createdAt).toLocaleDateString()}
                          {pb.description && ` · ${pb.description}`}
                        </p>
                      </div>
                      <div className="flex gap-1.5 shrink-0">
                        <Button size="sm" variant="outline" className="h-7 px-2.5 text-xs gap-1" onClick={() => openEditPlaybook(pb)}>
                          <Settings className="h-3 w-3" /> Edit
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 px-2.5 text-xs" title="Export as JSON" onClick={() => exportPlaybookAsJson(pb)}>
                          <Download className="h-3 w-3" />
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 px-2.5 text-xs" onClick={() => onDuplicatePlaybook(pb)}>
                          <Copy className="h-3 w-3" />
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 px-2.5 text-xs text-destructive border-destructive/30 hover:bg-destructive/10" onClick={() => onDeletePlaybook(pb.id)}>
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* PLAYBOOK EDITOR */}
          {playbookView === "edit" && (
            <section className="space-y-4">
              <div className="flex items-center gap-2">
                <Button size="sm" variant="ghost" className="h-8 px-2" onClick={() => setPlaybookView("list")}>
                  <ChevronRight className="h-4 w-4 rotate-180" />
                </Button>
                <h2 className="text-sm font-semibold text-foreground">
                  {activePlaybook ? "Edit Playbook" : "New Playbook"}
                </h2>
              </div>

              {/* Meta */}
              <div className="bg-card border border-border rounded-lg p-4 space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Playbook Name *</Label>
                    <Input placeholder="e.g. Deploy Application" value={playbookName} onChange={(e) => setPlaybookName(e.target.value)} className="bg-secondary/50 h-9" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Description</Label>
                    <Input placeholder="What this playbook does..." value={playbookDesc} onChange={(e) => setPlaybookDesc(e.target.value)} className="bg-secondary/50 h-9" />
                  </div>
                </div>
              </div>

              {/* Tasks */}
              <div className="bg-card border border-border rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Tasks ({playbookTasks.length})</h3>
                  <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={addPlaybookTask}>
                    <Plus className="h-3 w-3" /> Add Task
                  </Button>
                </div>

                <div className="space-y-2">
                  {playbookTasks.map((task, idx) => (
                    <div key={task.id} className="flex items-start gap-2 p-3 rounded-lg border border-border bg-secondary/10">
                      <div className="flex flex-col gap-1 pt-1.5 shrink-0">
                        <button onClick={() => moveTask(idx, -1)} disabled={idx === 0} className="text-muted-foreground hover:text-foreground disabled:opacity-20 transition-colors">
                          <ChevronDown className="h-3 w-3 rotate-180" />
                        </button>
                        <GripVertical className="h-3 w-3 text-muted-foreground/40 mx-auto" />
                        <button onClick={() => moveTask(idx, 1)} disabled={idx === playbookTasks.length - 1} className="text-muted-foreground hover:text-foreground disabled:opacity-20 transition-colors">
                          <ChevronDown className="h-3 w-3" />
                        </button>
                      </div>
                      <div className="flex-1 space-y-2">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-mono text-muted-foreground bg-secondary rounded px-1.5 py-0.5 shrink-0">#{idx + 1}</span>
                          <Input
                            placeholder="Description (optional)"
                            value={task.description}
                            onChange={(e) => updatePlaybookTask(task.id, { description: e.target.value })}
                            className="bg-secondary/50 h-7 text-xs flex-1"
                          />
                        </div>
                        <Input
                          placeholder="Command, e.g. systemctl restart nginx"
                          value={task.command}
                          onChange={(e) => updatePlaybookTask(task.id, { command: e.target.value })}
                          className="bg-background h-9 font-mono text-sm border-border"
                        />
                        <label className="text-[11px] flex items-center gap-1.5 text-muted-foreground cursor-pointer">
                          <input
                            type="checkbox"
                            checked={task.continueOnError}
                            onChange={(e) => updatePlaybookTask(task.id, { continueOnError: e.target.checked })}
                            className="rounded"
                          />
                          Continue on error
                        </label>
                      </div>
                      <button onClick={() => removePlaybookTask(task.id)} className="text-muted-foreground hover:text-destructive transition-colors pt-1.5 shrink-0">
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Target Servers */}
              <div className="bg-card border border-border rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Target Servers ({playbookTargets.size} selected)
                  </h3>
                  <div className="flex gap-1.5">
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={selectAllTargets}>Select Online</Button>
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={clearTargets}>Clear</Button>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  {servers.map((srv) => (
                    <button
                      key={srv.id}
                      onClick={() => toggleTarget(srv.id)}
                      className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg border text-left transition-all text-xs ${
                        playbookTargets.has(srv.id)
                          ? "border-primary bg-primary/5 text-foreground"
                          : "border-border bg-secondary/10 text-muted-foreground hover:text-foreground hover:border-border"
                      }`}
                    >
                      <StatusIndicator status={srv.status} showLabel={false} />
                      <span className="font-medium truncate">{srv.name}</span>
                      <span className="text-[10px] font-mono ml-auto opacity-60">{srv.host}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 justify-end">
                <Button size="sm" variant="outline" className="h-9 gap-1.5" onClick={onSavePlaybook} disabled={!playbookName.trim() || playbookTasks.length === 0}>
                  <Save className="h-3.5 w-3.5" /> Save Playbook
                </Button>
                <Button
                  size="sm"
                  className="h-9 gap-1.5 px-6"
                  onClick={onRunPlaybook}
                  disabled={playbookRunning || playbookTargets.size === 0 || playbookTasks.filter((t) => t.command.trim()).length === 0}
                >
                  <Play className="h-3.5 w-3.5" /> Run on {playbookTargets.size} Server{playbookTargets.size !== 1 ? "s" : ""}
                </Button>
              </div>
            </section>
          )}

          {/* PLAYBOOK RUN RESULTS */}
          {playbookView === "run" && (
            <section className="space-y-4">
              <div className="flex items-center gap-2">
                <Button size="sm" variant="ghost" className="h-8 px-2" onClick={() => setPlaybookView("edit")}>
                  <ChevronRight className="h-4 w-4 rotate-180" />
                </Button>
                <h2 className="text-sm font-semibold text-foreground">
                  Run Results {playbookRunning && <Loader2 className="inline h-3.5 w-3.5 ml-1.5 animate-spin text-primary" />}
                </h2>
                <span className="text-xs text-muted-foreground ml-auto">
                  {playbookResults.length} server{playbookResults.length !== 1 ? "s" : ""}
                </span>
              </div>

              {playbookResults.map((sr) => {
                const allDone = sr.taskResults.every((tr) => tr.status !== "pending" && tr.status !== "running");
                const allOk = sr.taskResults.every((tr) => tr.status === "success");
                const hasError = sr.taskResults.some((tr) => tr.status === "error");
                return (
                  <div key={sr.serverId} className="bg-card border border-border rounded-lg overflow-hidden">
                    <div className={`flex items-center gap-3 px-4 py-3 border-b border-border ${allDone ? (allOk ? "bg-primary/5" : hasError ? "bg-destructive/5" : "bg-secondary/20") : ""}`}>
                      <Server className="h-4 w-4 text-primary" />
                      <span className="text-sm font-medium text-foreground">{sr.serverName}</span>
                      <div className="ml-auto flex items-center gap-1.5">
                        {allDone && allOk && <CheckCircle2 className="h-4 w-4 text-primary" />}
                        {allDone && hasError && <XCircle className="h-4 w-4 text-destructive" />}
                        {!allDone && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                      </div>
                    </div>
                    <div className="divide-y divide-border">
                      {sr.taskResults.map((tr, ti) => (
                        <div key={tr.taskId} className="px-4 py-3">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-[10px] font-mono text-muted-foreground bg-secondary rounded px-1.5 py-0.5">#{ti + 1}</span>
                            <code className="text-xs font-mono text-foreground">{tr.command}</code>
                            <span className="ml-auto">
                              {tr.status === "success" && <CheckCircle2 className="h-3.5 w-3.5 text-primary" />}
                              {tr.status === "error" && <XCircle className="h-3.5 w-3.5 text-destructive" />}
                              {tr.status === "running" && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />}
                              {tr.status === "pending" && <span className="h-3.5 w-3.5 rounded-full bg-muted-foreground/20 inline-block" />}
                              {tr.status === "skipped" && <span className="text-[10px] text-muted-foreground">skipped</span>}
                            </span>
                          </div>
                          {tr.output && (
                            <pre className="mt-2 p-2.5 rounded bg-background border border-border text-[11px] font-mono text-muted-foreground overflow-x-auto max-h-32 whitespace-pre-wrap">{tr.output}</pre>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </section>
          )}
        </TabsContent>
      </Tabs>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingServer ? t("srv.edit_server") : t("srv.create_server")}</DialogTitle>
            <DialogDescription>{t("srv.server_settings")}</DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-5 max-h-[60vh] overflow-y-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5 md:col-span-2">
                <Label className="text-xs text-muted-foreground">{t("srv.name")} *</Label>
                <Input placeholder="e.g. prod-web-01" value={form.name} onChange={(e) => setForm((s) => ({ ...s, name: e.target.value }))} className="bg-secondary/50" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.host")} *</Label>
                <Input placeholder="192.168.1.10" value={form.host} onChange={(e) => setForm((s) => ({ ...s, host: e.target.value }))} className="bg-secondary/50" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.port")}</Label>
                <Input type="number" value={form.port} onChange={(e) => setForm((s) => ({ ...s, port: Number(e.target.value) || 22 }))} className="bg-secondary/50" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.username")} *</Label>
                <Input placeholder="ubuntu" value={form.username} onChange={(e) => setForm((s) => ({ ...s, username: e.target.value }))} className="bg-secondary/50" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Type</Label>
                <select
                  value={form.server_type}
                  onChange={(e) => setForm((s) => ({ ...s, server_type: e.target.value as "ssh" | "rdp" }))}
                  className="flex h-10 w-full rounded-md border border-input bg-secondary/50 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="ssh">SSH</option>
                  <option value="rdp">RDP</option>
                </select>
              </div>
            </div>

            <div className="border-t border-border pt-4 space-y-4">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Authentication</Label>
                <div className="flex gap-2">
                  {(["password", "key", "key_password"] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setForm((s) => ({ ...s, auth_method: m }))}
                      className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${form.auth_method === m ? "bg-primary/15 border-primary text-primary" : "bg-secondary/50 border-border text-muted-foreground hover:text-foreground"}`}
                    >
                      {m === "password" ? "Password" : m === "key" ? "SSH Key" : "Key + Pass"}
                    </button>
                  ))}
                </div>
              </div>

              {form.auth_method !== "password" && (
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.key_path")}</Label>
                  <Input placeholder="/home/user/.ssh/id_rsa" value={form.key_path} onChange={(e) => setForm((s) => ({ ...s, key_path: e.target.value }))} className="bg-secondary/50" />
                </div>
              )}
              {form.auth_method !== "key" && (
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">{t("srv.password")}</Label>
                  <Input
                    type="password"
                    placeholder={editingServer ? "Leave empty to keep" : ""}
                    value={form.password}
                    onChange={(e) => setForm((s) => ({ ...s, password: e.target.value }))}
                    className="bg-secondary/50"
                  />
                </div>
              )}
            </div>

            <div className="border-t border-border pt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.groups")}</Label>
                <select
                  value={form.group_id ?? ""}
                  onChange={(e) => setForm((s) => ({ ...s, group_id: e.target.value ? Number(e.target.value) : null }))}
                  className="flex h-10 w-full rounded-md border border-input bg-secondary/50 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="">{t("srv.no_group")}</option>
                  {groups
                    .filter((g) => g.id !== null)
                    .map((g) => (
                      <option key={g.id!} value={g.id!}>{g.name}</option>
                    ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">{t("srv.tags")}</Label>
                <Input placeholder="web, production" value={form.tags} onChange={(e) => setForm((s) => ({ ...s, tags: e.target.value }))} className="bg-secondary/50" />
              </div>
              <div className="space-y-1.5 md:col-span-2">
                <Label className="text-xs text-muted-foreground">{t("srv.notes")}</Label>
                <Input placeholder="..." value={form.notes} onChange={(e) => setForm((s) => ({ ...s, notes: e.target.value }))} className="bg-secondary/50" />
              </div>
            </div>
          </DialogBody>

          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setDialogOpen(false)}>
              {t("srv.cancel")}
            </Button>
            <Button size="sm" onClick={onSave} disabled={saving || !form.name || !form.host || !form.username}>
              {saving ? t("srv.saving") : editingServer ? t("srv.update") : t("srv.create")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <DialogContent className="max-w-5xl h-[85vh] flex flex-col p-0">
          {/* Header */}
          <div className="flex items-center gap-3 px-6 py-4 border-b border-border shrink-0">
            <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <Server className="h-4 w-4 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <DialogTitle className="text-sm font-semibold">{advancedServer?.name || "Server"}</DialogTitle>
              <DialogDescription className="text-xs font-mono mt-0">
                {advancedServer?.host}:{advancedServer?.port} · {advancedServer?.group_name}
              </DialogDescription>
            </div>
          </div>

          {advancedLoading ? (
            <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">{t("loading")}</div>
          ) : (
            <div className="flex flex-1 min-h-0">
              {/* Sidebar tabs */}
              <div className="w-44 shrink-0 border-r border-border bg-secondary/20 py-2">
                {([
                  { key: "access", icon: <Sparkles className="h-3.5 w-3.5" />, label: t("srv.access") },
                  { key: "knowledge", icon: <Sparkles className="h-3.5 w-3.5" />, label: t("srv.knowledge") },
                  { key: "context", icon: <Layers className="h-3.5 w-3.5" />, label: t("srv.context") },
                  { key: "security", icon: <Settings className="h-3.5 w-3.5" />, label: t("srv.security") },
                  { key: "execute", icon: <Terminal className="h-3.5 w-3.5" />, label: t("srv.execute") },
                ] as const).map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setAdvancedTab(tab.key)}
                    className={`w-full flex items-center gap-2.5 px-4 py-2.5 text-xs font-medium transition-colors text-left ${
                      advancedTab === tab.key
                        ? "bg-primary/10 text-primary border-r-2 border-primary"
                        : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                    }`}
                  >
                    {tab.icon}
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Content area */}
              <div className="flex-1 overflow-y-auto p-6">
                {/* ACCESS TAB */}
                {advancedTab === "access" && (
                  <div className="space-y-5">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground mb-1">{t("srv.server_sharing")}</h3>
                      <p className="text-xs text-muted-foreground mb-4">Share server access with other users</p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">{t("srv.username")}</Label>
                          <Input placeholder="username / email / id" value={shareUser} onChange={(e) => setShareUser(e.target.value)} className="bg-secondary/50 h-9" />
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">Expires</Label>
                          <Input type="datetime-local" value={shareExpiresAt} onChange={(e) => setShareExpiresAt(e.target.value)} className="bg-secondary/50 h-9" />
                        </div>
                      </div>
                      <div className="flex items-center justify-between mt-3">
                        <label className="text-xs flex items-center gap-2 text-muted-foreground">
                          <input type="checkbox" checked={shareContext} onChange={(e) => setShareContext(e.target.checked)} className="rounded" />
                          {t("srv.share_context")}
                        </label>
                        <Button size="sm" className="h-8 px-4" onClick={onShareCreate}>{t("srv.share")}</Button>
                      </div>
                    </div>

                    {shares.length > 0 && (
                      <div className="border-t border-border pt-4">
                        <h4 className="text-xs font-medium text-muted-foreground mb-3 uppercase tracking-wider">Active shares</h4>
                        <div className="space-y-2">
                          {shares.map((s) => (
                            <div key={s.id} className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-border bg-secondary/10">
                              <div className="h-7 w-7 rounded-full bg-primary/15 flex items-center justify-center text-xs font-medium text-primary shrink-0">
                                {(s.username || "U").slice(0, 1).toUpperCase()}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-foreground truncate">{s.username}</p>
                                <p className="text-xs text-muted-foreground">{s.email || "—"} · {s.is_active ? "active" : "expired"}</p>
                              </div>
                              <Button size="sm" variant="outline" className="h-7 text-xs text-destructive border-destructive/30 hover:bg-destructive/10" onClick={() => onShareRevoke(s.id)}>
                                {t("srv.revoke")}
                              </Button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* KNOWLEDGE TAB */}
                {advancedTab === "knowledge" && (
                  <div className="space-y-5">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground mb-1">{t("srv.ai_memory")}</h3>
                      <p className="text-xs text-muted-foreground mb-4">Knowledge entries for AI assistant context</p>
                      <div className="space-y-3">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">Title</Label>
                            <Input placeholder="Entry title" value={knowledgeTitle} onChange={(e) => setKnowledgeTitle(e.target.value)} className="bg-secondary/50 h-9" />
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">Category</Label>
                            <select
                              value={knowledgeCategory}
                              onChange={(e) => setKnowledgeCategory(e.target.value)}
                              className="flex h-9 w-full rounded-md border border-input bg-secondary/50 px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                            >
                              <option value="system">System</option>
                              <option value="services">Services</option>
                              <option value="network">Network</option>
                              <option value="security">Security</option>
                              <option value="performance">Performance</option>
                              <option value="storage">Storage</option>
                              <option value="packages">Packages</option>
                              <option value="config">Config</option>
                              <option value="issues">Issues</option>
                              <option value="solutions">Solutions</option>
                              <option value="other">Other</option>
                            </select>
                          </div>
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">Content</Label>
                          <Textarea placeholder="Knowledge content..." value={knowledgeContent} onChange={(e) => setKnowledgeContent(e.target.value)} className="bg-secondary/50 min-h-20 text-sm" />
                        </div>
                        <div className="flex justify-end">
                          <Button size="sm" className="h-8 px-4" onClick={onKnowledgeCreate}>{t("srv.add_entry")}</Button>
                        </div>
                      </div>
                    </div>

                    {knowledge.length > 0 && (
                      <div className="border-t border-border pt-4">
                        <h4 className="text-xs font-medium text-muted-foreground mb-3 uppercase tracking-wider">Entries ({knowledge.length})</h4>
                        <div className="space-y-2">
                          {knowledge.map((k) => (
                            <div key={k.id} className="flex items-start gap-3 px-3 py-3 rounded-lg border border-border bg-secondary/10">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                  <p className="text-sm font-medium text-foreground">{k.title}</p>
                                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${k.is_active ? "bg-primary/15 text-primary" : "bg-secondary text-muted-foreground"}`}>
                                    {k.category_label}
                                  </span>
                                </div>
                                <p className="text-xs text-muted-foreground leading-relaxed">{k.content}</p>
                              </div>
                              <div className="flex gap-1 shrink-0">
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => onKnowledgeToggle(k)}>
                                  {k.is_active ? t("srv.disable") : t("srv.enable")}
                                </Button>
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => { setKnowledgeEditingId(k.id); void onKnowledgeEdit(k); }}>
                                  {t("srv.edit")}
                                </Button>
                                <Button size="sm" variant="outline" className="h-7 px-2 text-xs text-destructive border-destructive/30 hover:bg-destructive/10" onClick={() => onKnowledgeDelete(k.id)}>
                                  {t("srv.delete")}
                                </Button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* CONTEXT TAB */}
                {advancedTab === "context" && (
                  <div className="space-y-6">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground mb-1">{t("srv.global_context")}</h3>
                      <p className="text-xs text-muted-foreground mb-4">Rules and constraints applied to all servers</p>
                      <div className="space-y-3">
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">Rules</Label>
                          <Textarea className="min-h-20 bg-secondary/50 text-sm" value={globalRules} onChange={(e) => setGlobalRules(e.target.value)} placeholder="Global rules for AI assistant" />
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">Forbidden commands</Label>
                            <Textarea className="min-h-20 bg-secondary/50 text-sm font-mono" value={globalForbidden} onChange={(e) => setGlobalForbidden(e.target.value)} placeholder="rm -rf /&#10;dd if=..." />
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">Required checks</Label>
                            <Textarea className="min-h-20 bg-secondary/50 text-sm font-mono" value={globalRequired} onChange={(e) => setGlobalRequired(e.target.value)} placeholder="uptime&#10;df -h" />
                          </div>
                        </div>
                        <div className="space-y-1.5">
                          <Label className="text-xs text-muted-foreground">Environment variables (JSON)</Label>
                          <Textarea className="min-h-16 bg-secondary/50 text-sm font-mono" value={globalEnvJson} onChange={(e) => setGlobalEnvJson(e.target.value)} placeholder='{"KEY": "value"}' />
                        </div>
                        <div className="flex justify-end">
                          <Button size="sm" className="h-8 px-4" onClick={onSaveGlobalContext}>{t("srv.save_global")}</Button>
                        </div>
                      </div>
                    </div>

                    {advancedServer?.group_id && (
                      <div className="border-t border-border pt-5">
                        <h3 className="text-sm font-semibold text-foreground mb-1">{t("srv.group_context")}</h3>
                        <p className="text-xs text-muted-foreground mb-4">Rules specific to group "{advancedServer.group_name}"</p>
                        <div className="space-y-3">
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">Group rules</Label>
                            <Textarea className="min-h-20 bg-secondary/50 text-sm" value={groupRules} onChange={(e) => setGroupRules(e.target.value)} placeholder="Group-specific rules" />
                          </div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">Forbidden commands</Label>
                              <Textarea className="min-h-20 bg-secondary/50 text-sm font-mono" value={groupForbidden} onChange={(e) => setGroupForbidden(e.target.value)} placeholder="One per line" />
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">Environment (JSON)</Label>
                              <Textarea className="min-h-20 bg-secondary/50 text-sm font-mono" value={groupEnvJson} onChange={(e) => setGroupEnvJson(e.target.value)} placeholder='{"KEY": "value"}' />
                            </div>
                          </div>
                          <div className="flex justify-end">
                            <Button size="sm" className="h-8 px-4" onClick={onSaveGroupContext}>{t("srv.save_group")}</Button>
                          </div>
                        </div>

                        {/* Group members */}
                        <div className="border-t border-border pt-4 mt-4">
                          <h4 className="text-xs font-medium text-muted-foreground mb-3 uppercase tracking-wider">Group members</h4>
                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">Username / email</Label>
                              <Input placeholder="user@example.com" value={groupMemberUser} onChange={(e) => setGroupMemberUser(e.target.value)} className="bg-secondary/50 h-9" />
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">Role</Label>
                              <select
                                value={groupMemberRole}
                                onChange={(e) => setGroupMemberRole(e.target.value as ServerGroupRole)}
                                className="flex h-9 w-full rounded-md border border-input bg-secondary/50 px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                              >
                                <option value="owner">Owner</option>
                                <option value="admin">Admin</option>
                                <option value="member">Member</option>
                                <option value="viewer">Viewer</option>
                              </select>
                            </div>
                            <div className="flex items-end">
                              <Button size="sm" className="h-9 w-full" onClick={onAddGroupMember}>{t("srv.add_member")}</Button>
                            </div>
                          </div>
                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
                            <div className="space-y-1.5">
                              <Label className="text-xs text-muted-foreground">Remove by user ID</Label>
                              <Input placeholder="user id" value={groupRemoveUserId} onChange={(e) => setGroupRemoveUserId(e.target.value)} className="bg-secondary/50 h-9" />
                            </div>
                            <div className="flex items-end">
                              <Button size="sm" variant="outline" className="h-9 w-full text-destructive border-destructive/30 hover:bg-destructive/10" onClick={onRemoveGroupMember}>{t("srv.remove_member")}</Button>
                            </div>
                            <div className="flex items-end gap-2">
                              <Button size="sm" variant="outline" className="h-9 flex-1" onClick={() => subscribeServerGroup(advancedServer.group_id!, "follow")}>{t("srv.follow_group")}</Button>
                              <Button size="sm" variant="outline" className="h-9 flex-1" onClick={() => subscribeServerGroup(advancedServer.group_id!, "favorite")}>{t("srv.fav_group")}</Button>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* SECURITY TAB */}
                {advancedTab === "security" && (
                  <div className="space-y-6">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground mb-1">{t("srv.master_pw")}</h3>
                      <p className="text-xs text-muted-foreground mb-4">Session-level master password for encrypted credentials</p>
                      <div className="space-y-3">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
                          <span className={`inline-block w-2 h-2 rounded-full ${hasMasterPassword ? "bg-primary" : "bg-muted-foreground"}`} />
                          {hasMasterPassword ? "Master password is set for this session" : "No master password set"}
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
                          <div className="space-y-1.5">
                            <Label className="text-xs text-muted-foreground">Master Password</Label>
                            <Input type="password" value={masterPassword} onChange={(e) => setMasterPasswordText(e.target.value)} className="bg-secondary/50 h-9" placeholder="Enter password" />
                          </div>
                          <Button size="sm" className="h-9" onClick={onSetMasterPassword}>{t("srv.set_mp")}</Button>
                          <Button size="sm" variant="outline" className="h-9" onClick={onClearMasterPassword}>{t("srv.clear_mp")}</Button>
                        </div>
                      </div>
                    </div>

                    <div className="border-t border-border pt-5">
                      <h3 className="text-sm font-semibold text-foreground mb-1">{t("srv.reveal_pw")}</h3>
                      <p className="text-xs text-muted-foreground mb-4">Decrypt and reveal stored server password</p>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
                        <div className="sm:col-span-2 space-y-1.5">
                          <Label className="text-xs text-muted-foreground">Decrypted password</Label>
                          <Input value={revealedPassword} readOnly className="bg-secondary/50 h-9 font-mono" placeholder="•••••••••" />
                        </div>
                        <Button size="sm" className="h-9" onClick={onRevealPassword}>{t("srv.reveal_pw")}</Button>
                      </div>
                    </div>
                  </div>
                )}

                {/* EXECUTE TAB */}
                {advancedTab === "execute" && (
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground mb-1">{t("srv.exec_cmd")}</h3>
                      <p className="text-xs text-muted-foreground mb-4">Run a quick command on this server</p>
                      <div className="flex gap-2">
                        <Input value={execCommand} onChange={(e) => setExecCommand(e.target.value)} className="bg-secondary/50 h-9 font-mono flex-1" placeholder="hostname" />
                        <Button size="sm" className="h-9 px-6" onClick={onExecuteCommand}>{t("srv.run")}</Button>
                      </div>
                    </div>
                    {execResult && (
                      <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">Output</Label>
                        <Textarea className="min-h-40 bg-background font-mono text-xs border-border" value={execResult} readOnly />
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
