import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useLocation } from "react-router-dom";

export type AssistantPageContext = {
  /** Short machine tag, e.g. "servers", "agent-run", "insights" */
  surface: string;
  /** Human path title */
  title?: string;
  /** Extra entity ids for the model */
  entity?: {
    serverId?: number;
    serverName?: string;
    agentId?: number;
    agentName?: string;
    runId?: number;
    pipelineId?: number;
    playbookId?: number;
    playbookName?: string;
  };
  /** Suggested quick chips for this surface */
  chips?: Array<{ id: string; labelRu: string; labelEn: string; promptRu: string; promptEn: string }>;
};

type AssistantShellValue = {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
  pageContext: AssistantPageContext;
  setPageContext: (ctx: Partial<AssistantPageContext> | null) => void;
  seedPrompt: string | null;
  consumeSeedPrompt: () => string | null;
  askWithPrompt: (prompt: string) => void;
};

const AssistantShellContext = createContext<AssistantShellValue | null>(null);

function surfaceFromPath(pathname: string): AssistantPageContext {
  const parts = pathname.split("/").filter(Boolean);
  const root = parts[0] ?? "dashboard";

  if (root === "servers" && parts[1] && parts[2] === "terminal") {
    const serverId = Number(parts[1]);
    return {
      surface: "terminal",
      title: "Terminal",
      entity: Number.isFinite(serverId) ? { serverId } : undefined,
      chips: [
        {
          id: "disks",
          labelRu: "Проверь диски",
          labelEn: "Check disks",
          promptRu: "Проверь диски на этом сервере: df -h, inode, самые тяжёлые каталоги.",
          promptEn: "Check disks on this server: df -h, inodes, heaviest dirs.",
        },
        {
          id: "load",
          labelRu: "Нагрузка",
          labelEn: "Load average",
          promptRu: "Покажи среднюю нагрузку, процессы с максимальной нагрузкой на CPU и память, а также отклонения.",
          promptEn: "Show load average, top CPU/RAM processes, and anything unusual.",
        },
        {
          id: "logs",
          labelRu: "Логи за час",
          labelEn: "Logs (1h)",
          promptRu: "Что в системных логах за последний час? Коротко по ошибкам.",
          promptEn: "What is in system logs for the last hour? Focus on errors.",
        },
      ],
    };
  }

  if (root === "servers") {
    return {
      surface: "servers",
      title: "Servers",
      chips: [
        {
          id: "fleet",
          labelRu: "Состояние серверов",
          labelEn: "Fleet status",
          promptRu: "Кратко покажи доступность серверов, проблемные хосты и оповещения.",
          promptEn: "Short fleet status: online/offline, worst hosts, alerts.",
        },
        {
          id: "add",
          labelRu: "Добавить SSH",
          labelEn: "Add SSH",
          promptRu: "Помоги добавить SSH-сервер: какие данные нужны.",
          promptEn: "Help add a new SSH server: what to ask the operator.",
        },
      ],
    };
  }

  if (root === "agents" && parts[1] === "run" && parts[2]) {
    const runId = Number(parts[2]);
    return {
      surface: "agent-run",
      title: "Agent run",
      entity: Number.isFinite(runId) ? { runId } : undefined,
      chips: [
        {
          id: "why",
          labelRu: "Почему упал?",
          labelEn: "Why failed?",
          promptRu: "Почему этот прогон завершился ошибкой? Разбери шаги и укажи первопричину.",
          promptEn: "Why did this run fail? Review steps and give root cause.",
        },
        {
          id: "retry",
          labelRu: "Исправить и повторить",
          labelEn: "Retry with fix",
          promptRu: "Предложи исправление и безопасный повторный запуск.",
          promptEn: "Suggest a fix and a safe way to re-run.",
        },
      ],
    };
  }

  if (root === "agents") {
    return {
      surface: "agents",
      title: "Agents",
      chips: [
        {
          id: "list",
          labelRu: "Список агентов",
          labelEn: "List agents",
          promptRu: "Покажи агентов и текущие запуски.",
          promptEn: "List agents and who is running now.",
        },
        {
          id: "backup",
          labelRu: "Проверка резервных копий",
          labelEn: "Backup template",
          promptRu: "Создай агента для проверки резервных копий на выбранных серверах.",
          promptEn: "Create a mini-agent that verifies backups on selected servers.",
        },
      ],
    };
  }

  if (root === "monitoring") {
    return {
      surface: "insights",
      title: "Insights",
      chips: [
        {
          id: "explain",
          labelRu: "Объясни прогноз",
          labelEn: "Explain forecast",
          promptRu: "Объясни ближайшие прогнозы: что критично и почему.",
          promptEn: "Explain nearest forecasts: what is critical and why.",
        },
        {
          id: "prevent",
          labelRu: "Что сделать заранее",
          labelEn: "Preventive",
          promptRu: "Что сделать заранее с учётом текущих прогнозов?",
          promptEn: "What preventive actions should we take from current forecasts?",
        },
      ],
    };
  }

  if (root === "automation") {
    const playbookId = parts[1] === "playbooks" ? Number(parts[2]) : Number.NaN;
    return {
      surface: "automation",
      title: "Ansible",
      entity: Number.isInteger(playbookId) && playbookId > 0 ? { playbookId } : undefined,
      chips: [
        {
          id: "explain-playbook",
          labelRu: "Что делает сценарий?",
          labelEn: "What does it do?",
          promptRu: "Кратко объясни выбранный сценарий Ansible, его риски и требования перед запуском.",
          promptEn: "Briefly explain what the selected playbook does, its risks, and prerequisites.",
        },
      ],
    };
  }

  if (root === "studio") {
    return {
      surface: "studio",
      title: "Studio",
      chips: [
        {
          id: "pipeline",
          labelRu: "Новый пайплайн",
          labelEn: "New pipeline",
          promptRu: "Помоги спроектировать пайплайн: цель, узлы, риски.",
          promptEn: "Help design a pipeline: goal, nodes, risks.",
        },
      ],
    };
  }

  if (root === "chat") {
    return { surface: "chat", title: "Chat" };
  }

  return {
    surface: root,
    title: root,
    chips: [
      {
        id: "brief",
        labelRu: "Сводка",
        labelEn: "Briefing",
        promptRu: "Краткая сводка: серверы, оповещения и агенты.",
        promptEn: "Short operator briefing: fleet, alerts, agents.",
      },
    ],
  };
}

export function AssistantShellProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [override, setOverride] = useState<Partial<AssistantPageContext> | null>(null);
  const [seedPrompt, setSeedPrompt] = useState<string | null>(null);

  const routeContext = useMemo(() => surfaceFromPath(location.pathname), [location.pathname]);

  const pageContext = useMemo<AssistantPageContext>(() => {
    if (!override) return routeContext;
    return {
      ...routeContext,
      ...override,
      entity: { ...routeContext.entity, ...override.entity },
      chips: override.chips ?? routeContext.chips,
    };
  }, [override, routeContext]);

  const setPageContext = useCallback((ctx: Partial<AssistantPageContext> | null) => {
    setOverride(ctx);
  }, []);

  const toggle = useCallback(() => setOpen((v) => !v), []);

  const consumeSeedPrompt = useCallback(() => {
    const value = seedPrompt;
    setSeedPrompt(null);
    return value;
  }, [seedPrompt]);

  const askWithPrompt = useCallback((prompt: string) => {
    setSeedPrompt(prompt);
    setOpen(true);
  }, []);

  const value = useMemo(
    () => ({
      open,
      setOpen,
      toggle,
      pageContext,
      setPageContext,
      seedPrompt,
      consumeSeedPrompt,
      askWithPrompt,
    }),
    [open, toggle, pageContext, setPageContext, seedPrompt, consumeSeedPrompt, askWithPrompt],
  );

  return <AssistantShellContext.Provider value={value}>{children}</AssistantShellContext.Provider>;
}

export function useAssistantShell() {
  const ctx = useContext(AssistantShellContext);
  if (!ctx) {
    throw new Error("useAssistantShell must be used within AssistantShellProvider");
  }
  return ctx;
}

/** Safe variant for optional use outside provider (returns null). */
export function useOptionalAssistantShell() {
  return useContext(AssistantShellContext);
}
