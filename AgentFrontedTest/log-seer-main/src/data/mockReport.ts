import type { Severity } from "@/lib/severity";

export interface TimelineEvent {
  id: string;
  time: string;
  source: string;
  message: string;
  severity: Severity;
  object: string;
  raw: string;
}

export interface Signal {
  id: string;
  source: string;
  time: string;
  text: string;
  severity: Severity;
}

export interface ActionStep {
  id: string;
  priority: "P0" | "P1" | "P2";
  title: string;
  description: string;
  owner: string;
  done: boolean;
}

export interface Artifact {
  id: string;
  name: string;
  type: string;
  size: string;
  date: string;
  description: string;
}

export interface AgentStep {
  id: string;
  index: number;
  title: string;
  command: string;
  status: Severity; // success | high(warning/errors) | critical(timeout)
  statusLabel: string;
  duration: string;
  details: string;
}

export const report = {
  status: "Завершён",
  title: "Инцидент: OOM и перезапуск web-prod-02",
  subtitle:
    "Контейнер nginx завершён из-за нехватки памяти; systemd перезапустил сервис через 4 секунды.",
  severity: "critical" as Severity,
  confidence: 92,
  meta: {
    server: "linux",
    container: "web-prod-02",
    window: "23:07:08–23:07:12",
    analysisDuration: "19 с",
    finishedAt: "16.06.2026 23:12:47 UTC+3",
  },
};

export const kpis = [
  {
    id: "root",
    label: "Корневая причина",
    value: "OOM",
    hint: "Out of memory",
    severity: "critical" as Severity,
  },
  {
    id: "service",
    label: "Затронут сервис",
    value: "nginx",
    hint: "1 контейнер",
    severity: "high" as Severity,
  },
  {
    id: "downtime",
    label: "Простой",
    value: "4 с",
    hint: "до авто-рестарта",
    severity: "high" as Severity,
  },
  {
    id: "events",
    label: "События",
    value: "16",
    hint: "из них 4 критичных",
    severity: "info" as Severity,
  },
];

export const summary =
  "В 23:07:08 ядро зафиксировало нехватку памяти на узле web-prod-02. OOM-killer завершил рабочий процесс nginx (PID 32145), после чего systemd автоматически перезапустил сервис. Полный простой составил около 4 секунд, потери данных не зафиксированы.";

export const rootCause =
  "Рабочий процесс nginx превысил доступный лимит памяти cgroup на фоне всплеска одновременных соединений. Ядро вызвало OOM-killer (fatal signal 5), который завершил процесс с наибольшим потреблением памяти. Так как сервис управляется systemd с политикой restart=on-failure, контейнер был поднят повторно через 4 секунды.";

export const signals: Signal[] = [
  {
    id: "s1",
    source: "kernel",
    time: "23:07:08",
    text: "Out of memory: Kill process 32145 (nginx) score 901",
    severity: "fatal",
  },
  {
    id: "s2",
    source: "dmesg",
    time: "23:07:09",
    text: "Killed process 32145 (nginx) total-vm:2.1GB anon-rss:1.9GB",
    severity: "high",
  },
  {
    id: "s3",
    source: "systemd",
    time: "23:07:12",
    text: "web-prod-02.service: scheduled restart, restart counter at 1",
    severity: "high",
  },
  {
    id: "s4",
    source: "cgroup",
    time: "23:07:08",
    text: "memory.limit_in_bytes достигнут: 2048MB / 2048MB",
    severity: "info",
  },
];

export const timeline: TimelineEvent[] = [
  {
    id: "t1",
    time: "22:42:11",
    source: "sshd",
    message: "Принят вход по SSH пользователя linux",
    severity: "info",
    object: "session/8841",
    raw: "Accepted publickey for linux from 10.0.4.12 port 51344 ssh2",
  },
  {
    id: "t2",
    time: "23:07:08",
    source: "kernel",
    message: "Fatal signal 5 — нехватка памяти (OOM)",
    severity: "fatal",
    object: "node/web-prod-02",
    raw: "kernel: Out of memory: Killed process 32145 (nginx), fatal signal 5",
  },
  {
    id: "t3",
    time: "23:07:09",
    source: "dmesg",
    message: "OOM-killer завершил процесс nginx PID 32145",
    severity: "high",
    object: "pid/32145",
    raw: "dmesg: Killed process 32145 (nginx) total-vm:2100000kB",
  },
  {
    id: "t4",
    time: "23:07:12",
    source: "systemd",
    message: "Контейнер web-prod-02 перезапущен",
    severity: "high",
    object: "web-prod-02.service",
    raw: "systemd: web-prod-02.service: scheduled restart, restart counter at 1",
  },
  {
    id: "t5",
    time: "23:07:12",
    source: "nginx",
    message: "Рабочий процесс завершён по сигналу 9",
    severity: "info",
    object: "worker/4",
    raw: "nginx: worker process 32145 exited on signal 9",
  },
];

export const actionPlan: ActionStep[] = [
  {
    id: "a1",
    priority: "P0",
    title: "Поднять memory limit для web-prod-02",
    description: "Увеличить memory.limit с 2 ГБ до 4 ГБ и перезапустить сервис.",
    owner: "SRE / linux",
    done: false,
  },
  {
    id: "a2",
    priority: "P1",
    title: "Проверить cgroup, top и free",
    description: "Снять профиль потребления памяти под нагрузкой, найти утечки.",
    owner: "Платформа",
    done: false,
  },
  {
    id: "a3",
    priority: "P1",
    title: "Проверить количество nginx workers",
    description: "Сопоставить worker_processes и worker_connections с лимитами.",
    owner: "Backend",
    done: false,
  },
  {
    id: "a4",
    priority: "P2",
    title: "Добавить алерты OOM / restart",
    description: "Настроить оповещения по событиям OOM-killer и авто-рестартам.",
    owner: "Observability",
    done: false,
  },
];

export const artifacts: Artifact[] = [
  {
    id: "f1",
    name: "report.pdf",
    type: "PDF-отчёт",
    size: "128 KB",
    date: "16.06.2026 23:12",
    description: "Итоговый отчёт по инциденту с выводами и планом действий.",
  },
  {
    id: "f2",
    name: "logs.tar.gz",
    type: "Архив логов",
    size: "24.8 MB",
    date: "16.06.2026 23:11",
    description: "Полная выгрузка системных и сервисных логов за окно инцидента.",
  },
  {
    id: "f3",
    name: "kernel-messages.log",
    type: "Журнал ядра",
    size: "512 KB",
    date: "16.06.2026 23:10",
    description: "Сообщения ядра, включая трассировку OOM-killer.",
  },
  {
    id: "f4",
    name: "run-context.json",
    type: "Контекст запуска",
    size: "85 KB",
    date: "16.06.2026 23:12",
    description: "Метаданные запуска агента, параметры и шаги анализа.",
  },
];

export const agentSteps: AgentStep[] = [
  {
    id: "g1",
    index: 1,
    title: "Сбор journalctl",
    command: "journalctl -u web-prod-02 --since 23:00 --until 23:15",
    status: "success",
    statusLabel: "Успешно",
    duration: "8m12s",
    details:
      "Получено 1 284 записей journald. Отфильтрованы события systemd и nginx в окне инцидента. Ключевые маркеры: scheduled restart, restart counter at 1.",
  },
  {
    id: "g2",
    index: 2,
    title: "Анализ dmesg",
    command: "dmesg --ctime | grep -i 'out of memory'",
    status: "success",
    statusLabel: "Успешно",
    duration: "4m23s",
    details:
      "Обнаружена запись OOM-killer: Killed process 32145 (nginx). total-vm 2.1GB, anon-rss 1.9GB. Подтверждает нехватку памяти на узле.",
  },
  {
    id: "g3",
    index: 3,
    title: "docker inspect",
    command: "docker inspect web-prod-02 --format '{{json .State}}'",
    status: "high",
    statusLabel: "С ошибками",
    duration: "6m05s",
    details:
      "Контейнер был перезапущен во время инспекции — часть полей State недоступна. ExitCode 137 (SIGKILL) получен из предыдущего состояния. Рекомендуется повторный сбор.",
  },
  {
    id: "g4",
    index: 4,
    title: "Сбор расширенных логов",
    command: "tar czf logs.tar.gz /var/log/{syslog,nginx,containers}",
    status: "critical",
    statusLabel: "Таймаут",
    duration: "15m00s",
    details:
      "Операция превысила лимит времени (900s) при упаковке /var/log/containers. Архив собран частично (24.8 MB). Полнота — около 86%.",
  },
  {
    id: "g5",
    index: 5,
    title: "Анализ и формирование отчёта",
    command: "webtermai analyze --context run-context.json",
    status: "success",
    statusLabel: "Успешно",
    duration: "9m02s",
    details:
      "Сопоставлены сигналы kernel/dmesg/systemd. Сформирован вывод о корневой причине OOM с уверенностью 92%. Сгенерированы report.pdf и план действий.",
  },
];
