import { Button, Field } from "@/components/ui";
import type { Details } from "@/api/intelligence";
import { list, record, text } from "./common";

export interface AgentRuntimeFieldsValue {
  sudo_policy: string;
  allow_multi_server: boolean;
  max_connections: number;
  input_artifacts: Details[];
  report_delivery: Details;
}
export function AgentRuntimeFields({
  value,
  onChange,
}: {
  value: AgentRuntimeFieldsValue;
  onChange: (next: AgentRuntimeFieldsValue) => void;
}) {
  const set = <K extends keyof AgentRuntimeFieldsValue>(
    key: K,
    next: AgentRuntimeFieldsValue[K],
  ) => onChange({ ...value, [key]: next });
  const telegram = record(value.report_delivery.telegram);
  const delivery = (key: string, next: unknown) =>
    set("report_delivery", {
      ...value.report_delivery,
      telegram: { ...telegram, [key]: next },
    });
  const material = (index: number, key: string, next: unknown) =>
    set(
      "input_artifacts",
      value.input_artifacts.map((item, i) =>
        i === index ? { ...item, [key]: next } : item,
      ),
    );
  return (
    <>
      <div className="intel-grid-2">
        <Field label="Политика sudo" htmlFor="agent-sudo">
          <select
            id="agent-sudo"
            value={value.sudo_policy}
            onChange={(e) => set("sudo_policy", e.target.value)}
          >
            <option value="disabled">Запрещено</option>
            <option value="ask">Запросить согласование</option>
            <option value="approved">Разрешено для выполнения</option>
          </select>
        </Field>
        <Field label="Одновременные подключения" htmlFor="agent-connections">
          <input
            id="agent-connections"
            type="number"
            min={1}
            max={10}
            value={value.max_connections}
            onChange={(e) => set("max_connections", Number(e.target.value))}
          />
        </Field>
      </div>
      <label className="intel-check">
        <input
          type="checkbox"
          checked={value.allow_multi_server}
          onChange={(e) => set("allow_multi_server", e.target.checked)}
        />
        Разрешить работу с несколькими серверами в выбранной области
      </label>
      <details>
        <summary>Материалы и чеклисты</summary>
        <div className="intel-form">
          <p className="muted">
            До 10 материалов. Документы и скрипты сохраняются как входные данные
            агента; добавление не запускает код.
          </p>
          {value.input_artifacts.map((item, index) => (
            <article
              className="intel-evidence intel-form"
              key={text(item.id, String(index))}
            >
              <div className="intel-row">
                <strong>Материал {index + 1}</strong>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    set(
                      "input_artifacts",
                      value.input_artifacts.filter((_, i) => i !== index),
                    )
                  }
                >
                  Убрать
                </Button>
              </div>
              <Field
                label="Название материала"
                htmlFor={`material-name-${index}`}
              >
                <input
                  id={`material-name-${index}`}
                  value={text(item.name, "")}
                  maxLength={120}
                  onChange={(e) => material(index, "name", e.target.value)}
                />
              </Field>
              <Field label="Тип материала" htmlFor={`material-kind-${index}`}>
                <select
                  id={`material-kind-${index}`}
                  value={text(item.kind, "document")}
                  onChange={(e) => material(index, "kind", e.target.value)}
                >
                  <option value="document">Документ</option>
                  <option value="task_list">Чеклист</option>
                  <option value="script">Готовый скрипт</option>
                </select>
              </Field>
              <Field
                label={item.kind === "script" ? "Код скрипта" : "Содержимое"}
                htmlFor={`material-content-${index}`}
              >
                <textarea
                  id={`material-content-${index}`}
                  className={item.kind === "script" ? "mono" : undefined}
                  rows={5}
                  maxLength={12000}
                  value={text(item.content, "")}
                  onChange={(e) => material(index, "content", e.target.value)}
                />
              </Field>
              {item.kind === "task_list" && (
                <>
                  <div className="intel-form">
                    {list(item.tasks).map((task, t) => (
                      <div key={t} className="intel-row">
                        <input
                          aria-label={`Пункт ${t + 1} материала ${index + 1}`}
                          value={text(task.title, "")}
                          maxLength={300}
                          onChange={(e) =>
                            material(
                              index,
                              "tasks",
                              list(item.tasks).map((v, i) =>
                                i === t ? { ...v, title: e.target.value } : v,
                              ),
                            )
                          }
                        />
                        <span className="muted">
                          {text(task.status, "pending")}
                        </span>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            material(
                              index,
                              "tasks",
                              list(item.tasks).filter((_, i) => i !== t),
                            )
                          }
                        >
                          Убрать пункт
                        </Button>
                      </div>
                    ))}
                  </div>
                  <Button
                    disabled={list(item.tasks).length >= 80}
                    onClick={() =>
                      material(index, "tasks", [
                        ...list(item.tasks),
                        {
                          title: "",
                          status: "pending",
                          details: "",
                          evidence: "",
                        },
                      ])
                    }
                  >
                    Добавить пункт чеклиста
                  </Button>
                </>
              )}
              <Field
                label="Указания по использованию"
                htmlFor={`material-hint-${index}`}
              >
                <input
                  id={`material-hint-${index}`}
                  value={text(item.run_hint, "")}
                  maxLength={500}
                  onChange={(e) => material(index, "run_hint", e.target.value)}
                />
              </Field>
            </article>
          ))}
          <Button
            disabled={value.input_artifacts.length >= 10}
            onClick={() =>
              set("input_artifacts", [
                ...value.input_artifacts,
                {
                  id: crypto.randomUUID(),
                  name: "",
                  kind: "document",
                  content: "",
                },
              ])
            }
          >
            Добавить материал
          </Button>
        </div>
      </details>
      <details>
        <summary>Доставка отчёта</summary>
        <div className="intel-form">
          <label className="intel-check">
            <input
              type="checkbox"
              checked={telegram.enabled === true}
              onChange={(e) => delivery("enabled", e.target.checked)}
            />
            Отправлять отчёт в Telegram после выполнения
          </label>
          {telegram.enabled === true && (
            <>
              <p className="notice">
                Отчёты могут содержать сведения об инфраструктуре. Выберите
                согласованный канал получателя.
              </p>
              <Field
                label="Telegram Chat ID"
                htmlFor="agent-telegram"
                description="Пустое поле использует получателя из ваших настроек уведомлений."
              >
                <input
                  id="agent-telegram"
                  value={text(telegram.chat_id, "")}
                  maxLength={120}
                  onChange={(e) => delivery("chat_id", e.target.value)}
                />
              </Field>
              <label className="intel-check">
                <input
                  type="checkbox"
                  checked={telegram.include_link !== false}
                  onChange={(e) => delivery("include_link", e.target.checked)}
                />
                Включать ссылку на полный отчёт
              </label>
            </>
          )}
        </div>
      </details>
    </>
  );
}
