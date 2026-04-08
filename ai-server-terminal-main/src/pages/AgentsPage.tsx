import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchAgents,
  fetchAgentTemplates,
  fetchFrontendBootstrap,
  createAgent,
  deleteAgent,
  runAgent,
  stopAgent,
  type AgentItem,
  type AgentTemplate,
  type AgentRunResult,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  Bot, Plus, Play, Trash2, RefreshCw, Clock, Zap, Eye,
  FileText, Server, X, Square,
  Brain, Target, Settings2, Layers, Terminal, CheckCircle2,
  AlertTriangle, Activity,
  Shield,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import ReactMarkdown from "react-markdown";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogBody, DialogFooter,
} from "@/components/ui/dialog";

function formatDuration(ms: number): string {
  if (!ms) return "—";
  if (ms < 1000) return `${ms}ms`;
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  return `${mins}m ${secs % 60}s`;
}

const MODE_ICONS: Record<string, typeof Bot> = { mini: Zap, full: Brain, multi: Layers };
const AGENT_ICONS: Record<string, LucideIcon> = {
  security_audit: Shield,
  security_patrol: Shield,
  log_analyzer: FileText,
  log_investigator: FileText,
  performance: Activity,
  disk_report: Server,
  docker_status: Layers,
  service_health: Settings2,
  deploy_watcher: Zap,
  infra_scout: Server,
  multi_health: Activity,
  custom: Settings2,
};
const FULL_AGENT_TOOL_OPTIONS = [
  { key: "open_connection", label: "Open connection" },
  { key: "close_connection", label: "Close connection" },
  { key: "ssh_execute", label: "SSH execute" },
  { key: "read_console", label: "Read console" },
  { key: "wait_for_output", label: "Wait for output" },
  { key: "send_ctrl_c", label: "Send Ctrl+C" },
  { key: "report", label: "Progress report" },
  { key: "ask_user", label: "Ask user" },
  { key: "analyze_output", label: "Analyze output" },
  { key: "list_skills", label: "List skills" },
  { key: "read_skill", label: "Read skill" },
] as const;

function buildDefaultToolsConfig() {
  return Object.fromEntries(FULL_AGENT_TOOL_OPTIONS.map((tool) => [tool.key, true]));
}

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function formatRoleLabel(role: string): string {
  return role
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export default function AgentsPage() {
  useI18n();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [modeFilter, setModeFilter] = useState<"all" | "mini" | "full" | "multi">("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [createdAgentId, setCreatedAgentId] = useState<number | null>(null);
  const [runningId, setRunningId] = useState<number | null>(null);
  const [result, setResult] = useState<AgentRunResult | null>(null);
  const [reportModalOpen, setReportModalOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["agents", "list"],
    queryFn: () => fetchAgents(),
    refetchInterval: 10_000,
  });

  const agents = (data?.agents || []).filter(
    (a) => modeFilter === "all" || a.mode === modeFilter,
  );

  const onRun = async (ag: AgentItem) => {
    setRunningId(ag.id);
    setResult(null);
    try {
      const res = await runAgent(ag.id);
      if (res.runs?.length > 0) {
        setResult(res.runs[0]);
        setReportModalOpen(true);
      }
      if ((ag.mode === "full" || ag.mode === "multi") && res.run_id) {
        navigate(`/agents/run/${res.run_id}`);
        return;
      }
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    } catch {
      setResult({ run_id: 0, server_name: "Error", status: "failed", ai_analysis: "Run failed.", duration_ms: 0, commands_output: [] });
    } finally {
      setRunningId(null);
    }
  };

  const onStop = async (ag: AgentItem) => {
    await stopAgent(ag.id);
    await queryClient.invalidateQueries({ queryKey: ["agents"] });
  };

  const onDelete = async (id: number) => {
    if (!confirm("Delete this agent?")) return;
    await deleteAgent(id);
    await queryClient.invalidateQueries({ queryKey: ["agents"] });
  };

  if (isLoading) return <div className="p-6 text-sm text-muted-foreground">Loading...</div>;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bot className="h-5 w-5 text-primary" />
          <h1 className="text-xl font-semibold text-foreground">Agents</h1>
          <span className="text-xs text-muted-foreground bg-secondary px-2 py-0.5 rounded">{agents.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-md border border-border overflow-hidden text-[11px] font-semibold">
            {(["all", "mini", "full", "multi"] as const).map((m) => (
              <button key={m} onClick={() => setModeFilter(m)}
                className={`px-2.5 py-1 transition-colors ${modeFilter === m ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground"}`}
              >{m === "all" ? "All" : m === "mini" ? "Mini" : m === "full" ? "Full" : "Pipeline"}</button>
            ))}
          </div>
          <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => queryClient.invalidateQueries({ queryKey: ["agents"] })}>
            <RefreshCw className="h-3 w-3" />
          </Button>
          <Button size="sm" className="h-7 text-xs gap-1" onClick={() => setCreateOpen(true)}>
            <Plus className="h-3 w-3" /> New Agent
          </Button>
        </div>
      </div>

      {result && !reportModalOpen && (
        <div className="bg-card border border-primary/20 rounded-lg px-4 py-2.5 flex items-center gap-3">
          <div className={`h-6 w-6 rounded-full flex items-center justify-center shrink-0 ${result.status === "completed" ? "bg-green-500/15" : "bg-red-500/15"}`}>
            {result.status === "completed" ? <CheckCircle2 className="h-3.5 w-3.5 text-green-400" /> : <AlertTriangle className="h-3.5 w-3.5 text-red-400" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm text-foreground">{result.server_name}</div>
            <div className="text-[11px] text-muted-foreground">{result.status} · {formatDuration(result.duration_ms)}</div>
          </div>
          <Button size="sm" variant="outline" className="h-8 gap-1.5 shrink-0" onClick={() => setReportModalOpen(true)}>
            <FileText className="h-3 w-3" /> Report
          </Button>
          <Button size="sm" variant="ghost" className="h-7 px-1.5 shrink-0 text-muted-foreground" onClick={() => setResult(null)}>
            <X className="h-3 w-3" />
          </Button>
        </div>
      )}

      {result && (
        <ReportModal result={result} open={reportModalOpen} onClose={() => setReportModalOpen(false)} />
      )}
      {agents.length === 0 ? (
        <div className="bg-card border border-border rounded-lg p-8 text-center">
          <Bot className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
          <p className="text-sm text-muted-foreground mb-3">No agents yet</p>
          <Button size="sm" onClick={() => setCreateOpen(true)} className="gap-1">
            <Plus className="h-3 w-3" /> Create your first agent
          </Button>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <div className="divide-y divide-border/50">
            {agents.map((ag) => {
              const ModeIcon = MODE_ICONS[ag.mode] || Zap;
              const AgentIcon = AGENT_ICONS[ag.agent_type] || Settings2;
              const isRunning = runningId === ag.id || !!ag.active_run_id;
              return (
                <div
                  key={ag.id}
                  className={`flex items-center gap-3 px-4 py-3 transition-colors ${
                    createdAgentId === ag.id
                      ? "bg-primary/8 ring-1 ring-inset ring-primary/25"
                      : "hover:bg-secondary/20"
                  }`}
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border/70 bg-card/70">
                    <AgentIcon className="h-4 w-4 text-primary" />
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-sm font-medium text-foreground">{ag.name}</span>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase ${ag.mode === "full" ? "bg-purple-500/20 text-purple-400" : ag.mode === "multi" ? "bg-violet-500/20 text-violet-400" : "bg-blue-500/20 text-blue-400"}`}>
                        <ModeIcon className="inline h-2.5 w-2.5 mr-0.5" />{ag.mode === "multi" ? "Pipeline" : ag.mode}
                      </span>
                      <span className="text-[9px] px-1 py-0.5 rounded bg-secondary text-muted-foreground">{ag.agent_type_display}</span>
                      {ag.active_run_id && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-green-500/20 text-green-400 font-bold animate-pulse">RUNNING</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-muted-foreground mt-0.5">
                      <span className="flex items-center gap-0.5"><Server className="h-2.5 w-2.5" /> {ag.server_count} servers</span>
                      {ag.last_run_at && <span className="flex items-center gap-0.5"><Clock className="h-2.5 w-2.5" /> {relativeTime(ag.last_run_at)}</span>}
                      {ag.schedule_minutes > 0 && <span className="flex items-center gap-0.5"><RefreshCw className="h-2.5 w-2.5" /> every {ag.schedule_minutes}m</span>}
                      {(ag.mode === "full" || ag.mode === "multi") && <span className="flex items-center gap-0.5"><Target className="h-2.5 w-2.5" /> {ag.mode === "multi" ? "Pipeline" : `${ag.max_iterations} iters`}</span>}
                    </div>
                    {ag.goal && <p className="text-[10px] text-muted-foreground mt-0.5 truncate max-w-md">{ag.goal}</p>}
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {ag.active_run_id ? (
                      <>
                        <Link to={`/agents/run/${ag.active_run_id}`}>
                          <Button size="sm" variant="outline" className="h-7 text-[10px] px-2 gap-1">
                            <Eye className="h-3 w-3" /> Watch
                          </Button>
                        </Link>
                        <Button size="sm" variant="outline" className="h-7 text-[10px] px-2 gap-1 text-red-400" onClick={() => onStop(ag)}>
                          <Square className="h-3 w-3" /> Stop
                        </Button>
                      </>
                    ) : (
                      <>
                        {ag.last_run_id && (
                          <Link to={`/agents/run/${ag.last_run_id}`}>
                            <Button size="sm" variant="ghost" className="h-7 text-[10px] px-2 gap-1 text-muted-foreground hover:text-foreground">
                              <FileText className="h-3 w-3" /> Report
                            </Button>
                          </Link>
                        )}
                        <Button size="sm" variant="outline" className="h-7 text-[10px] px-2 gap-1" disabled={isRunning} onClick={() => onRun(ag)}>
                          {isRunning ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} Run
                        </Button>
                      </>
                    )}
                    <Button size="sm" variant="ghost" className="h-7 px-1 text-muted-foreground hover:text-red-400" onClick={() => onDelete(ag.id)}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <CreateAgentDialog open={createOpen} onClose={() => setCreateOpen(false)}
        onCreated={async ({ id, mode }) => {
          setModeFilter("all");
          setCreatedAgentId(id);
          setCreateOpen(false);
          await queryClient.invalidateQueries({ queryKey: ["agents", "list"] });
          if (mode === "full" || mode === "multi") {
            navigate("/agents");
          }
          window.setTimeout(() => setCreatedAgentId((current) => (current === id ? null : current)), 8000);
        }} />
    </div>
  );
}

// ---------------------------------------------------------------------------

function CreateAgentDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (created: { id: number; mode: "mini" | "full" | "multi" }) => Promise<void> | void;
}) {
  const [step, setStep] = useState<"template" | "config">("template");
  const [mode, setMode] = useState<"mini" | "full" | "multi">("mini");
  const [selectedType, setSelectedType] = useState("");
  const [name, setName] = useState("");
  const [commands, setCommands] = useState("");
  const [aiPrompt, setAiPrompt] = useState("");
  const [goal, setGoal] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [maxIter, setMaxIter] = useState(20);
  const [multiServer, setMultiServer] = useState(false);
  const [toolsConfig, setToolsConfig] = useState<Record<string, boolean>>(() => buildDefaultToolsConfig());
  const [stopConditionsText, setStopConditionsText] = useState("");
  const [sessionTimeoutSeconds, setSessionTimeoutSeconds] = useState(600);
  const [maxConnections, setMaxConnections] = useState(5);
  const [selectedServers, setSelectedServers] = useState<number[]>([]);
  const [schedule, setSchedule] = useState(0);
  const [saving, setSaving] = useState(false);

  const { data: tplData } = useQuery({ queryKey: ["agents", "templates"], queryFn: fetchAgentTemplates, enabled: open });
  const { data: bootstrapData } = useQuery({ queryKey: ["frontend", "bootstrap"], queryFn: fetchFrontendBootstrap, staleTime: 30_000 });

  const templates = (tplData?.templates || []).filter((template) => template.mode === mode || (mode === "multi" && template.mode === "full"));
  const servers = bootstrapData?.servers || [];

  const onSelectTemplate = (tpl: AgentTemplate) => {
    setSelectedType(tpl.type);
    setName(tpl.name);
    setCommands(tpl.commands.join("\n"));
    setAiPrompt(tpl.ai_prompt);
    if (tpl.mode === "full" || mode === "multi") {
      setGoal(tpl.goal || "");
      setSystemPrompt(tpl.system_prompt || "");
      setMultiServer(tpl.allow_multi_server || false);
      setStopConditionsText((tpl.stop_conditions || []).join("\n"));
    }
    setStep("config");
  };

  const onSave = async () => {
    setSaving(true);
    try {
      const cmdList = commands.split("\n").map((c) => c.trim()).filter(Boolean);
      const created = await createAgent({
        name: name || "Custom Agent",
        mode,
        agent_type: selectedType || "custom",
        server_ids: selectedServers,
        commands: cmdList,
        ai_prompt: aiPrompt,
        schedule_minutes: schedule,
        goal,
        system_prompt: systemPrompt,
        max_iterations: maxIter,
        allow_multi_server: multiServer,
        tools_config: mode === "mini" ? {} : toolsConfig,
        stop_conditions: stopConditionsText.split("\n").map((item) => item.trim()).filter(Boolean),
        session_timeout_seconds: sessionTimeoutSeconds,
        max_connections: maxConnections,
      });
      await onCreated({ id: created.id, mode });
      resetForm();
    } finally { setSaving(false); }
  };

  const resetForm = () => {
    setStep("template"); setMode("mini"); setSelectedType(""); setName("");
    setCommands(""); setAiPrompt(""); setGoal(""); setSystemPrompt("");
    setMaxIter(20); setMultiServer(false); setSelectedServers([]); setSchedule(0);
    setToolsConfig(buildDefaultToolsConfig()); setStopConditionsText(""); setSessionTimeoutSeconds(600); setMaxConnections(5);
  };

  const toggleServer = (id: number) => setSelectedServers((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  const selectAll = () => { if (selectedServers.length === servers.length) setSelectedServers([]); else setSelectedServers(servers.map((s) => s.id)); };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{step === "template" ? "Create Agent" : `Configure ${mode === "multi" ? "Pipeline" : mode === "full" ? "Full" : "Mini"} Agent`}</DialogTitle>
        </DialogHeader>
        <DialogBody className="max-h-[70vh] overflow-y-auto">
          {step === "template" ? (
            <div className="space-y-4">
              {/* Mode selector */}
              <div className="flex gap-2 flex-wrap">
                <button onClick={() => setMode("mini")} className={`flex-1 min-w-[140px] text-left border rounded-lg p-3 transition-colors ${mode === "mini" ? "border-primary bg-primary/5" : "border-border hover:border-primary/30"}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <Zap className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Mini Agent</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">Run a list of commands and get AI analysis. Simple and fast.</p>
                </button>
                <button onClick={() => setMode("full")} className={`flex-1 min-w-[140px] text-left border rounded-lg p-3 transition-colors ${mode === "full" ? "border-primary bg-primary/5" : "border-border hover:border-primary/30"}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <Brain className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Full Agent (ReAct)</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">Autonomous agent with goal, reasoning loop, and multi-server support.</p>
                </button>
                <button onClick={() => setMode("multi")} className={`flex-1 min-w-[140px] text-left border rounded-lg p-3 transition-colors ${mode === "multi" ? "border-violet-500 bg-violet-500/5" : "border-border hover:border-violet-500/30"}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <Layers className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Multi-Agent Pipeline</span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">Orchestrator breaks goal into tasks. Each task runs a separate AI agent. Best for complex goals.</p>
                </button>
                </div>

              <div className="grid grid-cols-2 gap-2">
                {templates.map((tpl) => (
                  <button key={tpl.type} onClick={() => onSelectTemplate(tpl)}
                    className="text-left bg-secondary/30 border border-border rounded-lg p-3 hover:border-primary/50 transition-colors">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-transparent bg-background/30 text-muted-foreground">
                        {(() => {
                          const TemplateIcon = AGENT_ICONS[tpl.type] || Settings2;
                          return <TemplateIcon className="h-4 w-4" />;
                        })()}
                      </span>
                      <span className="text-sm font-medium text-foreground">{tpl.name}</span>
                    </div>
                    <p className="text-[10px] text-muted-foreground">
                      {tpl.mode === "full"
                        ? ((tpl.goal || "Autonomous ReAct agent").slice(0, 100))
                        : `${tpl.command_count} commands`}
                    </p>
                  </button>
                ))}
                <button onClick={() => { setSelectedType("custom"); setStep("config"); }}
                  className="text-left bg-secondary/30 border border-border rounded-lg p-3 hover:border-primary/50 transition-colors">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg">🔧</span>
                    <span className="text-sm font-medium text-foreground">
                      {mode === "full" ? "Custom Full Agent" : mode === "multi" ? "Custom Pipeline Agent" : "Custom Mini Agent"}
                    </span>
                  </div>
                  <p className="text-[10px] text-muted-foreground">Build from scratch</p>
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Name</label>
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="My Agent" className="bg-secondary/50 h-8 text-sm" />
              </div>

              {(mode === "full" || mode === "multi") && (
                <>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                      <Target className="h-3 w-3" /> Goal
                      {mode === "multi" && <span className="text-[9px] text-violet-400 bg-violet-500/10 px-1 rounded">Orchestrator will decompose this into tasks</span>}
                    </label>
                    <Textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} className="bg-secondary/50 text-xs"
                      placeholder={mode === "multi" ? "Describe the complex goal. E.g.: 'Perform a full security audit: check users, open ports, failed logins, suspicious processes and provide recommendations.'" : "What should this agent achieve? Be specific about the end result."} />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground flex items-center gap-1"><Settings2 className="h-3 w-3" /> System Prompt (optional)</label>
                    <Textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={2} className="bg-secondary/50 text-xs"
                      placeholder="Custom role/personality for the agent" />
                  </div>
                  <div className="flex gap-4">
                    <div className="flex-1 space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">Max Iterations</label>
                      <Input type="number" min={1} max={100} value={maxIter} onChange={(e) => setMaxIter(Number(e.target.value))} className="bg-secondary/50 h-8 text-sm" />
                    </div>
                    <div className="flex-1 space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">Session Timeout (sec)</label>
                      <Input type="number" min={30} max={3600} value={sessionTimeoutSeconds} onChange={(e) => setSessionTimeoutSeconds(Number(e.target.value))} className="bg-secondary/50 h-8 text-sm" />
                    </div>
                    <div className="flex-1 space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">Max Connections</label>
                      <Input type="number" min={1} max={10} value={maxConnections} onChange={(e) => setMaxConnections(Number(e.target.value))} className="bg-secondary/50 h-8 text-sm" />
                    </div>
                    <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer pt-5">
                      <input type="checkbox" checked={multiServer} onChange={(e) => setMultiServer(e.target.checked)} className="rounded" />
                      Multi-server
                    </label>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-muted-foreground">Stop Conditions</label>
                    <Textarea
                      value={stopConditionsText}
                      onChange={(e) => setStopConditionsText(e.target.value)}
                      rows={3}
                      className="bg-secondary/50 text-xs"
                      placeholder="One condition per line. Example: Health checks are green"
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-medium text-muted-foreground">Tool Access</label>
                      <button
                        type="button"
                        className="text-[10px] text-primary hover:underline"
                        onClick={() => setToolsConfig(buildDefaultToolsConfig())}
                      >
                        Enable all
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-2 rounded-lg border border-border/70 bg-secondary/20 p-3">
                      {FULL_AGENT_TOOL_OPTIONS.map((tool) => (
                        <label key={tool.key} className="flex items-center gap-2 text-xs text-muted-foreground">
                          <input
                            type="checkbox"
                            checked={Boolean(toolsConfig[tool.key])}
                            onChange={(event) =>
                              setToolsConfig((current) => ({ ...current, [tool.key]: event.target.checked }))
                            }
                          />
                          {tool.label}
                        </label>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {mode === "mini" && (
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Commands (one per line)</label>
                  <Textarea value={commands} onChange={(e) => setCommands(e.target.value)} rows={5} className="bg-secondary/50 font-mono text-[11px]"
                    placeholder="hostname&#10;uptime&#10;free -m" />
                </div>
              )}

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">AI Prompt</label>
                <Textarea value={aiPrompt} onChange={(e) => setAiPrompt(e.target.value)} rows={2} className="bg-secondary/50 text-xs"
                  placeholder="Extra instructions for AI analysis" />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Servers</label>
                <div className="flex flex-wrap gap-1.5">
                  <button onClick={selectAll} className={`px-2 py-1 text-[10px] rounded border transition-colors ${selectedServers.length === servers.length ? "border-primary text-primary" : "border-border text-muted-foreground"}`}>All</button>
                  {servers.map((s) => (
                    <button key={s.id} onClick={() => toggleServer(s.id)}
                      className={`px-2 py-1 text-[10px] rounded border transition-colors ${selectedServers.includes(s.id) ? "border-primary text-primary bg-primary/10" : "border-border text-muted-foreground"}`}>
                      {s.name}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-muted-foreground">Schedule</label>
                  <span className="text-xs font-mono text-foreground">{schedule === 0 ? "Manual" : `${schedule} min`}</span>
                </div>
                <input type="range" min={0} max={1440} step={5} value={schedule} onChange={(e) => setSchedule(Number(e.target.value))}
                  className="w-full h-1.5 bg-secondary rounded-full appearance-none cursor-pointer accent-primary" />
              </div>
            </div>
          )}
        </DialogBody>
        {step === "config" && (
          <DialogFooter>
            <Button size="sm" variant="outline" onClick={() => setStep("template")}>Back</Button>
            <Button size="sm" onClick={onSave} disabled={saving || !selectedServers.length}>
              {saving ? "Creating..." : "Create Agent"}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Full-screen Report Modal
// ---------------------------------------------------------------------------

function ReportModal({ result, open, onClose }: { result: AgentRunResult; open: boolean; onClose: () => void }) {
  const [activeTab, setActiveTab] = useState<"report" | "console">("report");
  const report = result.final_report || result.ai_analysis || "";
  const hasConsole = result.commands_output.length > 0;
  const isCompleted = result.status === "completed";

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="flex h-[90vh] w-[95vw] max-w-5xl flex-col gap-0 rounded-[1.75rem] p-0">
        <div className="flex shrink-0 items-center gap-3 border-b border-border bg-card px-5 py-3">
          <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${isCompleted ? "bg-green-500/10" : "bg-red-500/10"}`}>
            {isCompleted ? <CheckCircle2 className="h-4 w-4 text-green-400" /> : <AlertTriangle className="h-4 w-4 text-red-400" />}
          </div>
          <div className="flex-1 min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">Agent Report — {result.server_name}</p>
            <div className="mt-0.5 flex items-center gap-3 text-[10px] text-muted-foreground">
              <span className={`font-bold uppercase ${isCompleted ? "text-green-400" : "text-red-400"}`}>{result.status}</span>
              <span className="flex items-center gap-0.5"><Activity className="h-2.5 w-2.5" />{formatDuration(result.duration_ms)}</span>
              {hasConsole && <span className="flex items-center gap-0.5"><Terminal className="h-2.5 w-2.5" />{result.commands_output.length} commands</span>}
            </div>
          </div>
          <button onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        {hasConsole && (
          <div className="flex shrink-0 border-b border-border bg-card/50 px-5">
            <button
              onClick={() => setActiveTab("report")}
              className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${activeTab === "report" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              <FileText className="inline h-3 w-3 mr-1" />Report
            </button>
            <button
              onClick={() => setActiveTab("console")}
              className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${activeTab === "console" ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              <Terminal className="inline h-3 w-3 mr-1" />Console ({result.commands_output.length})
            </button>
          </div>
        )}

        <div className="flex-1 min-h-0 overflow-y-auto">
          {activeTab === "report" ? (
            <div className="py-8 px-8 max-w-[720px] mx-auto font-sans">
              {report ? (
                <div
                  className="
                    [&_h1]:text-[22px] [&_h1]:font-bold [&_h1]:text-foreground [&_h1]:leading-snug [&_h1]:mb-3 [&_h1]:mt-0
                    [&_h2]:text-[13px] [&_h2]:font-semibold [&_h2]:uppercase [&_h2]:tracking-widest [&_h2]:text-muted-foreground [&_h2]:mt-9 [&_h2]:mb-3 [&_h2]:pb-2 [&_h2]:border-b [&_h2]:border-border/30
                    [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-foreground [&_h3]:mt-6 [&_h3]:mb-2
                    [&_p]:text-[15px] [&_p]:text-foreground/80 [&_p]:leading-[1.8] [&_p]:mb-4
                    [&_ul]:mb-5 [&_ul]:pl-5 [&_ul]:space-y-1.5 [&_ul]:list-disc [&_ul]:marker:text-muted-foreground/60
                    [&_ol]:mb-5 [&_ol]:pl-5 [&_ol]:space-y-1.5 [&_ol]:list-decimal [&_ol]:marker:text-muted-foreground/60
                    [&_li]:text-[15px] [&_li]:text-foreground/80 [&_li]:leading-[1.8]
                    [&_strong]:font-semibold [&_strong]:text-foreground
                    [&_em]:italic [&_em]:text-foreground/65
                    [&_blockquote]:border-l-4 [&_blockquote]:border-primary/40 [&_blockquote]:pl-5 [&_blockquote]:py-2 [&_blockquote]:my-5 [&_blockquote]:bg-secondary/10 [&_blockquote]:rounded-r-lg [&_blockquote]:text-[15px] [&_blockquote]:text-foreground/70
                    [&_code]:text-[13px] [&_code]:font-mono [&_code]:bg-secondary/40 [&_code]:text-foreground/85 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded
                    [&_pre]:bg-secondary/20 [&_pre]:border [&_pre]:border-border/30 [&_pre]:rounded-xl [&_pre]:p-5 [&_pre]:overflow-x-auto [&_pre]:text-[12px] [&_pre]:font-mono [&_pre]:text-foreground/75 [&_pre]:my-5
                    [&_hr]:border-border/25 [&_hr]:my-8
                    [&_table]:w-full [&_table]:text-sm [&_table]:my-6 [&_table]:border-collapse [&_table]:border [&_table]:border-border/40 [&_table]:rounded-lg [&_table]:overflow-hidden
                    [&_thead]:bg-secondary/40
                    [&_th]:text-left [&_th]:px-4 [&_th]:py-2.5 [&_th]:text-[11px] [&_th]:font-semibold [&_th]:uppercase [&_th]:tracking-wide [&_th]:text-muted-foreground [&_th]:border [&_th]:border-border/30
                    [&_td]:px-4 [&_td]:py-3 [&_td]:text-[13px] [&_td]:text-foreground/80 [&_td]:border [&_td]:border-border/20 [&_td]:align-top [&_td]:leading-snug
                    [&_tr:nth-child(even)_td]:bg-secondary/10
                    [&_tr:hover_td]:bg-primary/5
                  "
                >
                  <ReactMarkdown>{report}</ReactMarkdown>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <FileText className="h-10 w-10 text-muted-foreground/30 mb-3" />
                  <p className="text-sm text-muted-foreground">No report available</p>
                </div>
              )}
            </div>
          ) : (
            <div className="p-4 space-y-3">
              {result.commands_output.map((cmd, i) => (
                <div key={i} className="bg-[#0d1117] rounded-lg overflow-hidden border border-border/30">
                  <div className="flex items-center gap-2 px-3 py-2 bg-secondary/10 border-b border-border/20">
                    <span className="text-green-400 font-mono text-[11px]">$</span>
                    <span className="font-mono text-xs text-foreground flex-1">{cmd.cmd}</span>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${cmd.exit_code === 0 ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"}`}>
                      exit {cmd.exit_code}
                    </span>
                    <span className="text-[9px] text-muted-foreground">{cmd.duration_ms}ms</span>
                  </div>
                  {cmd.stdout && (
                    <pre className="px-3 py-2.5 text-[11px] text-foreground/80 font-mono whitespace-pre-wrap overflow-x-auto">{cmd.stdout}</pre>
                  )}
                  {cmd.stderr && (
                    <pre className="px-3 py-2.5 text-[11px] text-red-400/80 font-mono whitespace-pre-wrap border-t border-red-500/10">{cmd.stderr}</pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
