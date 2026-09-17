import { localize } from "@/lib/i18n";
import type { KubernetesPodRef } from "@/api";
import { isPodReady } from "./types";

/** Technical copy for IT / DevOps — keep K8s terms, no metaphors. */
export function nsLabel(lang: string): string {
  return localize(lang, "Namespace", "Namespace");
}

export function nsHint(lang: string): string {
  return localize(
    lang,
    "Изоляция ресурсов внутри кластера. Типичные: production, staging, default.",
    "Resource isolation inside the cluster. Typical: production, staging, default.",
  );
}

export function clusterHint(lang: string): string {
  return localize(
    lang,
    "Кластер Kubernetes, к которому подключена платформа.",
    "The Kubernetes cluster this platform is connected to.",
  );
}

export function podWord(lang: string): string {
  return localize(lang, "Pod", "Pod");
}

export function podHint(lang: string): string {
  return localize(
    lang,
    "Запущенный экземпляр workload. При сбоях смотрите логи и events.",
    "A running workload instance. On failures check logs and events.",
  );
}

export function humanPodStatus(pod: KubernetesPodRef, lang: string): string {
  const phase = (pod.phase || "").toLowerCase();
  const health = (pod.health || "").toLowerCase();

  if (phase.includes("crash") || phase.includes("backoff")) {
    return localize(lang, "CrashLoopBackOff", "CrashLoopBackOff");
  }
  if (phase.includes("pending") || phase.includes("containercreating")) {
    return localize(lang, "Pending", "Pending");
  }
  if (phase.includes("failed") || health === "degraded" || health === "unhealthy") {
    return localize(lang, "Unhealthy", "Unhealthy");
  }
  if (phase.includes("succeeded") || phase.includes("completed")) {
    return localize(lang, "Succeeded", "Succeeded");
  }
  if (isPodReady(pod) || phase === "running") {
    return localize(lang, "Running", "Running");
  }
  return pod.phase || pod.health || localize(lang, "Unknown", "Unknown");
}

export function needsAttention(pod: KubernetesPodRef): boolean {
  if (!isPodReady(pod)) return true;
  const phase = (pod.phase || "").toLowerCase();
  return (
    phase.includes("crash") ||
    phase.includes("backoff") ||
    phase.includes("pending") ||
    phase.includes("failed") ||
    phase.includes("unknown")
  );
}

export type JourneyStepId = "cluster" | "namespace" | "pod" | "logs";

export function journeySteps(lang: string): Array<{ id: JourneyStepId; label: string; hint: string }> {
  return [
    {
      id: "cluster",
      label: localize(lang, "1. Кластер", "1. Cluster"),
      hint: localize(lang, "Целевой API-сервер", "Target API server"),
    },
    {
      id: "namespace",
      label: localize(lang, "2. Namespace", "2. Namespace"),
      hint: localize(lang, "Граница ресурсов", "Resource scope"),
    },
    {
      id: "pod",
      label: localize(lang, "3. Pod", "3. Pod"),
      hint: localize(lang, "Объект для диагностики", "Object to inspect"),
    },
    {
      id: "logs",
      label: localize(lang, "4. Логи", "4. Logs"),
      hint: localize(lang, "Вывод контейнера", "Container output"),
    },
  ];
}

export function nextStepMessage(input: {
  lang: string;
  hasClusters: boolean;
  clusterId: string;
  namespace: string;
  podId: string;
  hasLogs: boolean;
}): { step: JourneyStepId; title: string; body: string } {
  const { lang } = input;
  if (!input.hasClusters) {
    return {
      step: "cluster",
      title: localize(lang, "Подключите кластер", "Connect a cluster"),
      body: localize(
        lang,
        "Список пуст, пока нет подключения. Откройте вкладку «Подключение» и загрузите kubeconfig.",
        "The list stays empty until a connection exists. Open Connect and upload a kubeconfig.",
      ),
    };
  }
  if (!input.clusterId) {
    return {
      step: "cluster",
      title: localize(lang, "Выберите кластер", "Select a cluster"),
      body: localize(lang, "Укажите кластер для этой сессии.", "Choose the cluster for this session."),
    };
  }
  if (!input.namespace) {
    return {
      step: "namespace",
      title: localize(lang, "Выберите namespace", "Select a namespace"),
      body: localize(
        lang,
        "Ограничьте scope: production — боевые workload, staging — проверка.",
        "Narrow the scope: production for live workloads, staging for verification.",
      ),
    };
  }
  if (!input.podId) {
    return {
      step: "pod",
      title: localize(lang, "Выберите pod", "Select a pod"),
      body: localize(
        lang,
        "Начните с блока «Требуют внимания» — там обычно источник инцидента.",
        "Start with “Needs attention” — that is usually the incident source.",
      ),
    };
  }
  if (!input.hasLogs) {
    return {
      step: "logs",
      title: localize(lang, "Откройте логи, затем «Разобрать»", "Open logs, then Explain"),
      body: localize(
        lang,
        "Логи — stdout/stderr контейнера. ИИ выделит гипотезу и шаги проверки.",
        "Logs are container stdout/stderr. AI extracts a hypothesis and check steps.",
      ),
    };
  }
  return {
    step: "logs",
    title: localize(lang, "Продолжите диагностику", "Continue diagnosis"),
    body: localize(
      lang,
      "Смотрите вкладки «События» и «Exec» рядом с логами.",
      "Check the Events and Exec tabs next to the logs.",
    ),
  };
}
