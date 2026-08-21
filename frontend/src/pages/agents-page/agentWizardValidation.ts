import { BookOpen, CheckCircle2, Layers, Server, Tag, type LucideIcon } from "lucide-react";
import { z } from "zod";
import type { AgentScheduleConfig } from "@/lib/api";
import type { AgentSudoPolicy } from "./agentPageLabels";
import { isScheduleConfigValid } from "./agentPageSchedules";

export type AgentWizardStep = "template" | "basics" | "servers" | "capabilities" | "review";
export type AgentTargetScope = "external" | "servers";

export type AgentWizardCheckKey =
  | "scenario"
  | "behavior"
  | "commands"
  | "servers"
  | "sudo"
  | "schedule"
  | "telegram";

export type AgentWizardCheck = {
  key: AgentWizardCheckKey;
  step: AgentWizardStep;
  passed: boolean;
  labelRu: string;
  labelEn: string;
  detailRu: string;
  detailEn: string;
  risk?: "warning" | "danger";
};

export type AgentWizardReadinessInput = {
  selectedType: string;
  mode: "mini" | "full" | "multi";
  name: string;
  commands: string;
  goal: string;
  targetScope: AgentTargetScope;
  selectedServers: number[];
  hasServerDependentTools: boolean;
  hasServerDependentSkills: boolean;
  sudoPolicy: AgentSudoPolicy;
  sudoRiskAcknowledged: boolean;
  scheduleConfig: AgentScheduleConfig;
  schedule: number;
  telegramEnabled: boolean;
  telegramChatId: string;
};

export type AgentWizardValidationIssue = {
  step: AgentWizardStep;
  messageRu: string;
  messageEn: string;
};

export type AgentWizardValidationResult = {
  isValid: boolean;
  issues: AgentWizardValidationIssue[];
};

function commandLines(commands: string): string[] {
  return commands
    .split("\n")
    .map((command) => command.trim())
    .filter(Boolean);
}

function hasUnsafeCommand(commands: string): boolean {
  return commandLines(commands).some((command) =>
    /\b(rm\s+-rf|mkfs|dd\s+if=|shutdown|reboot|poweroff|systemctl\s+(restart|stop)|docker\s+(rm|stop|restart)|kubectl\s+delete)\b/i.test(command),
  );
}

export function validateAgentWizardSchema(input: AgentWizardReadinessInput): AgentWizardValidationResult {
  const schema = z
    .object({
      selectedType: z.string().trim().min(1),
      mode: z.enum(["mini", "full", "multi"]),
      name: z.string().trim().min(1),
      commands: z.string(),
      goal: z.string(),
      targetScope: z.enum(["external", "servers"]),
      selectedServers: z.array(z.number()),
      hasServerDependentTools: z.boolean(),
      hasServerDependentSkills: z.boolean(),
      sudoPolicy: z.enum(["disabled", "ask", "approved"]),
      sudoRiskAcknowledged: z.boolean(),
      scheduleConfig: z.custom<AgentScheduleConfig>(),
      schedule: z.number(),
      telegramEnabled: z.boolean(),
      telegramChatId: z.string(),
    })
    .superRefine((value, ctx) => {
      const commandsCount = commandLines(value.commands).length;
      const hasRunnableAction = value.mode === "mini"
        ? commandsCount > 0
        : commandsCount > 0 || Boolean(value.goal.trim());
      if (!hasRunnableAction) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["commands"], message: "runnable_action" });
      }
      const requiresServer = value.mode === "mini"
        || commandsCount > 0
        || value.sudoPolicy !== "disabled"
        || value.hasServerDependentTools
        || value.hasServerDependentSkills;
      const serverScopeValid = value.targetScope === "external"
        ? !requiresServer
        : value.selectedServers.length > 0;
      if (!serverScopeValid) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["selectedServers"], message: "server_scope_required" });
      }
      if (!isScheduleConfigValid(value.scheduleConfig, value.schedule)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["schedule"], message: "schedule_invalid" });
      }
      if ((value.sudoPolicy === "approved" || hasUnsafeCommand(value.commands)) && !value.sudoRiskAcknowledged) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["sudo"], message: "sudo_unacknowledged" });
      }
      if (value.telegramEnabled && !value.telegramChatId.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["telegram"], message: "telegram_missing" });
      }
    });
  const result = schema.safeParse(input);
  if (result.success) return { isValid: true, issues: [] };
  const issues = result.error.issues.map<AgentWizardValidationIssue>((issue) => {
    const field = String(issue.path[0] || "");
    if (field === "selectedType") return { step: "template", messageRu: "Выберите сценарий агента.", messageEn: "Choose an agent scenario." };
    if (field === "name") return { step: "basics", messageRu: "Укажите имя агента.", messageEn: "Enter an agent name." };
    if (field === "commands") return { step: "basics", messageRu: "Добавьте команду или цель агента.", messageEn: "Add a command or agent goal." };
    if (field === "selectedServers") return { step: "servers", messageRu: "Для выбранных SSH-возможностей нужен сервер.", messageEn: "The selected SSH capabilities require a server." };
    if (field === "schedule") return { step: "servers", messageRu: "Исправьте расписание.", messageEn: "Fix the schedule." };
    if (field === "sudo") return { step: "basics", messageRu: "Подтвердите sudo или опасные команды.", messageEn: "Acknowledge sudo or dangerous commands." };
    if (field === "telegram") return { step: "capabilities", messageRu: "Укажите Telegram Chat ID или выключите доставку.", messageEn: "Enter Telegram Chat ID or disable delivery." };
    return { step: "basics", messageRu: "Исправьте конфигурацию агента.", messageEn: "Fix the agent configuration." };
  });
  return { isValid: false, issues };
}

export function buildAgentWizardReadiness(input: AgentWizardReadinessInput): AgentWizardCheck[] {
  const hasScenario = Boolean(input.selectedType.trim());
  const hasName = Boolean(input.name.trim());
  const commandsCount = commandLines(input.commands).length;
  const hasRunnableAction = input.mode === "mini"
    ? commandsCount > 0
    : commandsCount > 0 || Boolean(input.goal.trim());
  const riskyCommands = hasUnsafeCommand(input.commands);
  const sudoRisk = input.sudoPolicy === "approved" || riskyCommands;
  const sudoPassed = !sudoRisk || input.sudoRiskAcknowledged;
  const schedulePassed = isScheduleConfigValid(input.scheduleConfig, input.schedule);
  const telegramPassed = !input.telegramEnabled || Boolean(input.telegramChatId.trim());
  const requiresServer = input.mode === "mini"
    || commandsCount > 0
    || input.sudoPolicy !== "disabled"
    || input.hasServerDependentTools
    || input.hasServerDependentSkills;
  const serverScopePassed = input.targetScope === "external"
    ? !requiresServer
    : input.selectedServers.length > 0;
  return [
    {
      key: "scenario",
      step: "template",
      passed: hasScenario,
      labelRu: "Сценарий выбран",
      labelEn: "Scenario selected",
      detailRu: hasScenario ? "Тип агента определён." : "Выберите шаблон или ручной сценарий.",
      detailEn: hasScenario ? "Agent type is set." : "Choose a template or custom scenario.",
    },
    {
      key: "behavior",
      step: "basics",
      passed: hasName,
      labelRu: "Название заполнено",
      labelEn: "Name provided",
      detailRu: hasName ? "Агент будет понятен в списке и отчётах." : "Укажите имя агента.",
      detailEn: hasName ? "The agent is identifiable in lists and reports." : "Enter an agent name.",
    },
    {
      key: "commands",
      step: "basics",
      passed: hasRunnableAction,
      labelRu: "Есть действие",
      labelEn: "Runnable action",
      detailRu: hasRunnableAction ? `${commandsCount} команд или цель агента.` : "Добавьте команду или цель для полного агента.",
      detailEn: hasRunnableAction ? `${commandsCount} commands or an agent goal.` : "Add a command or a goal for a full agent.",
      risk: riskyCommands ? "warning" : undefined,
    },
    {
      key: "servers",
      step: "servers",
      passed: serverScopePassed,
      labelRu: input.targetScope === "external" ? "Внешние системы" : "Серверы выбраны",
      labelEn: input.targetScope === "external" ? "External systems" : "Servers selected",
      detailRu: serverScopePassed
        ? (input.targetScope === "external" ? "SSH-сервер не требуется." : `${input.selectedServers.length} целей выбрано.`)
        : (input.targetScope === "external" ? "Команды, sudo или выбранные SSH-tools/skills требуют переключиться на серверы." : "Выберите минимум один сервер."),
      detailEn: serverScopePassed
        ? (input.targetScope === "external" ? "No SSH server is required." : `${input.selectedServers.length} targets selected.`)
        : (input.targetScope === "external" ? "Commands, sudo, or selected SSH tools/skills require server scope." : "Select at least one server."),
    },
    {
      key: "schedule",
      step: "servers",
      passed: schedulePassed,
      labelRu: "Расписание валидно",
      labelEn: "Schedule valid",
      detailRu: schedulePassed ? "Расписание можно сохранить." : "Заполните время, дни или дату запуска.",
      detailEn: schedulePassed ? "Schedule can be saved." : "Fill in time, weekdays, or run date.",
    },
    {
      key: "sudo",
      step: "basics",
      passed: sudoPassed,
      labelRu: "Риск sudo принят",
      labelEn: "Sudo risk acknowledged",
      detailRu: sudoPassed ? "Привилегированный запуск явно подтверждён или не требуется." : "Подтвердите риск sudo/опасных команд.",
      detailEn: sudoPassed ? "Privileged execution is acknowledged or not required." : "Acknowledge sudo/dangerous command risk.",
      risk: sudoRisk ? "danger" : undefined,
    },
    {
      key: "telegram",
      step: "capabilities",
      passed: telegramPassed,
      labelRu: "Telegram настроен",
      labelEn: "Telegram configured",
      detailRu: telegramPassed ? "Доставка отчёта корректна или выключена." : "Укажите Chat ID или выключите Telegram.",
      detailEn: telegramPassed ? "Report delivery is valid or disabled." : "Enter a Chat ID or disable Telegram.",
    },
  ];
}

export function readinessPercent(checks: AgentWizardCheck[]): number {
  if (!checks.length) return 0;
  return Math.round((checks.filter((check) => check.passed).length / checks.length) * 100);
}

export function firstFailedCheckForStep(checks: AgentWizardCheck[], step: AgentWizardStep): AgentWizardCheck | undefined {
  return checks.find((check) => check.step === step && !check.passed);
}

export function stepHasBlockingFailure(checks: AgentWizardCheck[], step: AgentWizardStep): boolean {
  return checks.some((check) => check.step === step && !check.passed);
}

export const AGENT_WIZARD_STEPS: Array<{
  key: AgentWizardStep;
  labelRu: string;
  labelEn: string;
  detailRu: string;
  detailEn: string;
  icon: LucideIcon;
}> = [
  { key: "basics", labelRu: "Задача", labelEn: "Task", detailRu: "Результат и правила", detailEn: "Outcome and rules", icon: Tag },
  { key: "servers", labelRu: "Системы", labelEn: "Systems", detailRu: "Доступ и запуск", detailEn: "Access and trigger", icon: Server },
  { key: "capabilities", labelRu: "Инструменты", labelEn: "Toolkit", detailRu: "Skills and context", detailEn: "Skills and context", icon: BookOpen },
  { key: "review", labelRu: "Результат", labelEn: "Result", detailRu: "Проверка и сохранение", detailEn: "Review and save", icon: CheckCircle2 },
];
