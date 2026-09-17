import { localize } from "@/lib/i18n";
import type { ExplainLogsInput, ExplainLogsResult } from "./types";

type MarkerRule = {
  id: string;
  pattern: RegExp;
  confidence: ExplainLogsResult["confidence"];
  causeRu: string;
  causeEn: string;
  checksRu: string[];
  checksEn: string[];
};

const MARKERS: MarkerRule[] = [
  {
    id: "CrashLoopBackOff",
    pattern: /crashloopbackoff|back-off restarting failed container/i,
    confidence: "high",
    causeRu: "Контейнер циклически падает и Kubernetes уходит в CrashLoopBackOff.",
    causeEn: "The container keeps crashing and Kubernetes entered CrashLoopBackOff.",
    checksRu: [
      "Просмотрите последние FATAL/ERROR строки в хвосте лога.",
      "Сверьте ConfigMap/Secret и переменные окружения приложения.",
      "Проверьте liveness/readiness probes и зависимые сервисы.",
    ],
    checksEn: [
      "Review the latest FATAL/ERROR lines in the log tail.",
      "Verify ConfigMap/Secret values and app environment variables.",
      "Check liveness/readiness probes and dependent services.",
    ],
  },
  {
    id: "OOMKilled",
    pattern: /oomkilled|out of memory|memory cgroup out of memory/i,
    confidence: "high",
    causeRu: "Процесс убит из‑за нехватки памяти (OOMKilled).",
    causeEn: "The process was killed due to memory pressure (OOMKilled).",
    checksRu: [
      "Сверьте memory requests/limits у контейнера.",
      "Ищите утечки или пики аллокаций в логах перед убийством.",
      "Сравните usage на соседних репликах того же Deployment.",
    ],
    checksEn: [
      "Compare memory requests/limits on the container.",
      "Look for allocation spikes in logs just before the kill.",
      "Compare usage against sibling replicas of the same Deployment.",
    ],
  },
  {
    id: "ImagePullBackOff",
    pattern: /imagepullbackoff|errimagepull|failed to pull image|manifest unknown/i,
    confidence: "high",
    causeRu: "Образ не удалось скачать (ImagePullBackOff / ErrImagePull).",
    causeEn: "The image could not be pulled (ImagePullBackOff / ErrImagePull).",
    checksRu: [
      "Проверьте имя/тег образа и доступ к registry.",
      "Сверьте imagePullSecrets и права сервис-аккаунта.",
      "Убедитесь, что тег существует и не private без credentials.",
    ],
    checksEn: [
      "Verify image name/tag and registry reachability.",
      "Check imagePullSecrets and service-account permissions.",
      "Confirm the tag exists and is not private without credentials.",
    ],
  },
  {
    id: "CreateContainerConfigError",
    pattern: /createcontainerconfigerror|secret .+ not found|configmap .+ not found/i,
    confidence: "high",
    causeRu: "Ошибка конфигурации контейнера (Secret/ConfigMap отсутствует).",
    causeEn: "Container config error (missing Secret/ConfigMap).",
    checksRu: [
      "Проверьте, что Secret/ConfigMap существуют в том же namespace.",
      "Сверьте имена ключей в volume/envFrom с реальными ключами.",
      "Посмотрите связанные Warning-события namespace.",
    ],
    checksEn: [
      "Confirm Secret/ConfigMap exist in the same namespace.",
      "Match volume/envFrom key names to real keys.",
      "Inspect related Warning events in the namespace.",
    ],
  },
  {
    id: "probe_failed",
    pattern: /liveness probe failed|readiness probe failed|probe failed/i,
    confidence: "medium",
    causeRu: "Probe падает — приложение не отвечает критерию health-check.",
    causeEn: "A probe is failing — the app does not meet the health-check criteria.",
    checksRu: [
      "Проверьте путь/порт probe и ответ приложения.",
      "Убедитесь, что зависимости (БД, кэш) доступны при старте.",
      "При необходимости временно ослабьте initialDelaySeconds только для диагностики.",
    ],
    checksEn: [
      "Verify probe path/port and the application response.",
      "Confirm dependencies (DB, cache) are reachable at startup.",
      "Only for diagnosis, consider temporary initialDelaySeconds relaxation.",
    ],
  },
  {
    id: "connection_refused",
    pattern: /connection refused|connect: connection refused|dial tcp .+: connect/i,
    confidence: "high",
    causeRu: "Приложение не может установить TCP-соединение с зависимостью.",
    causeEn: "The application cannot open a TCP connection to a dependency.",
    checksRu: [
      "Проверьте Service/Endpoints целевого хоста в namespace.",
      "Сверьте host/port в конфиге с актуальным адресом сервиса.",
      "Убедитесь, что целевой под/сервис Ready.",
    ],
    checksEn: [
      "Check Service/Endpoints for the target host in the namespace.",
      "Match host/port in config to the live service address.",
      "Confirm the target pod/service is Ready.",
    ],
  },
  {
    id: "permission_denied",
    pattern: /permission denied|forbidden|unauthorized|access denied/i,
    confidence: "medium",
    causeRu: "Отказ в доступе — права или credentials недостаточны.",
    causeEn: "Access denied — insufficient permissions or credentials.",
    checksRu: [
      "Проверьте RBAC / service account для пода.",
      "Сверьте токены/секреты, которые читает приложение.",
      "Посмотрите audit/события вокруг момента отказа.",
    ],
    checksEn: [
      "Check RBAC / service account for the pod.",
      "Verify tokens/secrets the application reads.",
      "Inspect audit/events around the denial.",
    ],
  },
  {
    id: "exit_code",
    pattern: /exit code [1-9]\d*|exited with code [1-9]\d*/i,
    confidence: "medium",
    causeRu: "Контейнер завершился с ненулевым exit code.",
    causeEn: "The container exited with a non-zero exit code.",
    checksRu: [
      "Найдите FATAL/ERROR перед выходом процесса.",
      "Сверьте команду entrypoint/args и рабочий каталог.",
      "Проверьте, не падает ли init из‑за миграций/конфига.",
    ],
    checksEn: [
      "Find FATAL/ERROR lines before process exit.",
      "Verify entrypoint/args and working directory.",
      "Check whether init fails on migrations/config.",
    ],
  },
];

export function explainLogsMock(input: ExplainLogsInput, lang: string = "ru"): ExplainLogsResult {
  const text = input.lines.join("\n");
  const matched = MARKERS.filter((rule) => rule.pattern.test(text));
  const signals = matched.map((rule) => rule.id);

  if (input.restartCount >= 5 && !signals.includes("CrashLoopBackOff")) {
    signals.push(`restarts:${input.restartCount}`);
  }
  if (input.phase && /crash|fail|error|backoff|pending/i.test(input.phase)) {
    signals.push(`phase:${input.phase}`);
  }

  const disclaimer = localize(
    lang,
    "Локальный анализ на фронте (mock). Не production AI и не мутирует кластер.",
    "Local frontend mock analysis. Not production AI and does not mutate the cluster.",
  );

  if (!matched.length) {
    const lowFromRestarts = input.restartCount >= 5;
    return {
      summary: localize(
        lang,
        lowFromRestarts
          ? `В хвосте нет явных маркеров сбоя, но у пода ${input.restartCount} рестартов — смотрите события и предыдущие контейнеры.`
          : "В хвосте лога недостаточно сигналов для уверенного диагноза.",
        lowFromRestarts
          ? `No clear failure markers in the log tail, but the pod has ${input.restartCount} restarts — check events and previous containers.`
          : "The log tail does not contain enough signals for a confident diagnosis.",
      ),
      likelyCause: localize(
        lang,
        lowFromRestarts
          ? "Возможна нестабильность без явных ERROR в текущем снимке."
          : "Причина по текущему снимку неочевидна.",
        lowFromRestarts
          ? "Instability is possible even without explicit ERROR lines in this snapshot."
          : "The cause is unclear from the current snapshot.",
      ),
      signals: signals.length ? signals : [],
      suggestedChecks: [
        localize(lang, "Обновите снимок логов и сравните с Warning-событиями namespace.", "Refresh the log snapshot and compare with namespace Warning events."),
        localize(lang, "Проверьте describe пода / предыдущий terminated container.", "Inspect pod describe / previous terminated container."),
        localize(lang, "Сверьте готовность зависимостей (Service, Endpoints).", "Verify dependency readiness (Service, Endpoints)."),
      ],
      confidence: lowFromRestarts ? "medium" : "low",
      disclaimer,
    };
  }

  const primary = matched[0];
  const confidence =
    matched.some((m) => m.confidence === "high") || input.restartCount >= 10
      ? "high"
      : matched.some((m) => m.confidence === "medium")
        ? "medium"
        : "low";

  const checks = lang === "ru" ? primary.checksRu : primary.checksEn;
  const extra = matched.slice(1).map((m) => m.id);

  return {
    summary: localize(
      lang,
      `Под ${input.namespace}/${input.podName}: найдены сигналы ${signals.join(", ")}.`,
      `Pod ${input.namespace}/${input.podName}: found signals ${signals.join(", ")}.`,
    ),
    likelyCause: lang === "ru" ? primary.causeRu : primary.causeEn,
    signals,
    suggestedChecks: [
      ...checks,
      ...(extra.length
        ? [
            localize(
              lang,
              `Дополнительно учтите маркеры: ${extra.join(", ")}.`,
              `Also account for markers: ${extra.join(", ")}.`,
            ),
          ]
        : []),
    ].slice(0, 5),
    confidence,
    disclaimer,
  };
}
