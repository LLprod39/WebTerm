import { FIXED_DATE } from "./platformFixtureTypes";

/**
 * Demo-only fixtures for the server "advanced" dialog: sharing, manual notes
 * (knowledge), and AI memory snapshots. Populated so the product-demo tour has
 * lifelike content on the Access + Knowledge tabs instead of empty states.
 *
 * Guarded behind PlatformMockOptions.demoData so regular e2e/visual tests keep
 * seeing the default empty responses.
 */

export interface DemoShare {
  id: number;
  user_id: number;
  username: string;
  email: string;
  share_context: boolean;
  can_connect_terminal: boolean;
  can_execute_command: boolean;
  can_read_files: boolean;
  can_write_files: boolean;
  expires_at: string | null;
  created_at: string | null;
  is_active: boolean;
}

export interface DemoKnowledgeItem {
  id: number;
  title: string;
  content: string;
  category: string;
  category_label: string;
  source: string;
  source_label: string;
  confidence: number;
  is_active: boolean;
  updated_at: string | null;
}

export interface DemoMemorySnapshot {
  id: number;
  title: string;
  content: string;
  memory_key: string;
  kind: "canonical" | "pattern" | "automation" | "skill_draft" | "manual_note" | "ai_note";
  version: number;
  confidence: number;
  freshness: number;
  updated_at: string | null;
  created_at: string | null;
  rewrite_reason: string;
}

export function makeServerDetailFixtures() {
  const demoShares: DemoShare[] = [
    {
      id: 501,
      user_id: 22,
      username: "m.orlova",
      email: "m.orlova@corp.io",
      share_context: true,
      can_connect_terminal: true,
      can_execute_command: false,
      can_read_files: true,
      can_write_files: false,
      expires_at: null,
      created_at: FIXED_DATE,
      is_active: true,
    },
    {
      id: 502,
      user_id: 27,
      username: "devops-oncall",
      email: "oncall@corp.io",
      share_context: true,
      can_connect_terminal: true,
      can_execute_command: true,
      can_read_files: true,
      can_write_files: false,
      expires_at: "2026-04-01T20:00:00.000Z",
      created_at: FIXED_DATE,
      is_active: true,
    },
  ];

  const demoKnowledge: DemoKnowledgeItem[] = [
    {
      id: 301,
      title: "Развёртывание nginx",
      content:
        "Конфиги в /etc/nginx/sites-enabled. После правок: nginx -t && systemctl reload nginx.\nCanary — сначала выкатываем на web-02, затем на прод.",
      category: "services",
      category_label: "Сервисы",
      source: "manual",
      source_label: "Вручную",
      confidence: 1,
      is_active: true,
      updated_at: FIXED_DATE,
    },
    {
      id: 302,
      title: "Ротация секретов",
      content:
        "Секреты живут в Vault по пути secret/web-01. Меняем каждые 30 дней.\nСледующая плановая ротация — 1 августа.",
      category: "security",
      category_label: "Безопасность",
      source: "manual",
      source_label: "Вручную",
      confidence: 1,
      is_active: true,
      updated_at: FIXED_DATE,
    },
  ];

  const demoKnowledgeCategories = [
    { value: "services", label: "Сервисы" },
    { value: "security", label: "Безопасность" },
    { value: "network", label: "Сеть" },
    { value: "other", label: "Другое" },
  ];

  const demoMemory: DemoMemorySnapshot[] = [
    {
      id: 701,
      title: "Профиль сервера",
      content:
        "Web-01 — прод веб-нода за балансировщиком. Nginx + PHP-FPM, реплика PostgreSQL.\nПиковый трафик 18:00–22:00 MSK.",
      memory_key: "summary",
      kind: "canonical",
      version: 3,
      confidence: 0.92,
      freshness: 0.85,
      updated_at: FIXED_DATE,
      created_at: FIXED_DATE,
      rewrite_reason: "",
    },
    {
      id: 702,
      title: "Доступ и сеть",
      content:
        "SSH только по ключу, порт 22. Наружу открыты 80/443.\nДоступ к БД разрешён из подсети 10.0.0.0/24.",
      memory_key: "access",
      kind: "canonical",
      version: 2,
      confidence: 0.88,
      freshness: 0.8,
      updated_at: FIXED_DATE,
      created_at: FIXED_DATE,
      rewrite_reason: "",
    },
    {
      id: 703,
      title: "Замеченные риски",
      content:
        "Раздел / заполняется логами PHP-FPM. При заполнении >85% ротировать /var/log.\nИнцидент 12.06 был из-за переполнения диска.",
      memory_key: "risks",
      kind: "canonical",
      version: 1,
      confidence: 0.9,
      freshness: 0.75,
      updated_at: FIXED_DATE,
      created_at: FIXED_DATE,
      rewrite_reason: "",
    },
    {
      id: 704,
      title: "Runbook: перезапуск nginx",
      content:
        "1) nginx -t 2) systemctl reload nginx 3) проверить curl -I localhost.\nВ пиковые часы не использовать restart — только reload.",
      memory_key: "runbook",
      kind: "pattern",
      version: 2,
      confidence: 0.86,
      freshness: 0.9,
      updated_at: FIXED_DATE,
      created_at: FIXED_DATE,
      rewrite_reason: "",
    },
  ];

  return { demoShares, demoKnowledge, demoKnowledgeCategories, demoMemory };
}
