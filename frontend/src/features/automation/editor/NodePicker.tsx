import { useEffect, useMemo, useRef, useState } from "react";
import { CornerDownLeft, Search, X } from "lucide-react";
import type { NodeManifest } from "@/api/automation";
import { Button } from "@/components/ui";
import {
  GROUP_LABELS,
  handleLabel,
  resolveCatalog,
  suggestNext,
  type CatalogEntry,
  type NodeGroup,
} from "./catalog";
import { PALETTE_MIME } from "./FlowCanvas";

export type PickerPending =
  | { kind: "output"; source: string; handle: string }
  | { kind: "insert"; edgeId: string }
  | { kind: "position"; x: number; y: number }
  | { kind: "free" }
  | null;

export interface PickerContext {
  /** Label of the node the new step will follow. */
  label: string;
  type: string;
  handle?: string;
}

type Item = { manifest: NodeManifest; entry: CatalogEntry };

const GROUP_ORDER: NodeGroup[] = [
  "ops",
  "agent",
  "logic",
  "output",
  "trigger",
  "default",
];

function riskOf(manifest: NodeManifest) {
  if (manifest.requires_approval_by_default)
    return { tone: "approval", text: "согласование" };
  if (manifest.mutates_state) return { tone: "mutates", text: "изменяет" };
  return { tone: "read", text: "чтение" };
}

export function NodePicker({
  open,
  manifests,
  pending,
  context,
  onClose,
  onPick,
}: {
  open: boolean;
  manifests: NodeManifest[];
  pending: PickerPending;
  context?: PickerContext;
  onClose: () => void;
  onPick: (manifest: NodeManifest) => void;
}) {
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<"steps" | "triggers">("steps");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);

  const all = useMemo<Item[]>(
    () =>
      manifests.map((manifest) => ({
        manifest,
        entry: resolveCatalog(manifest.type, manifest),
      })),
    [manifests],
  );

  const query = search.trim().toLowerCase();

  const filtered = useMemo(() => {
    return all.filter(({ entry, manifest }) => {
      const isTrigger = entry.group === "trigger";
      if (tab === "triggers" ? !isTrigger : isTrigger) return false;
      if (!query) return true;
      return `${entry.title} ${entry.description} ${manifest.type} ${manifest.category} ${manifest.tags.join(" ")}`
        .toLowerCase()
        .includes(query);
    });
  }, [all, query, tab]);

  const suggested = useMemo(() => {
    if (query || tab !== "steps") return [];
    const types = suggestNext(context?.type);
    return types
      .map((type) => filtered.find((item) => item.manifest.type === type))
      .filter((item): item is Item => Boolean(item));
  }, [context?.type, filtered, query, tab]);

  const sections = useMemo(() => {
    const map = new Map<NodeGroup, Item[]>();
    for (const item of filtered) {
      const list = map.get(item.entry.group) ?? [];
      list.push(item);
      map.set(item.entry.group, list);
    }
    const ordered: { key: string; title: string; items: Item[] }[] = [];
    if (suggested.length)
      ordered.push({ key: "suggested", title: "Рекомендуем", items: suggested });
    for (const group of GROUP_ORDER) {
      const items = map.get(group);
      if (items?.length)
        ordered.push({ key: group, title: GROUP_LABELS[group], items });
    }
    return ordered;
  }, [filtered, suggested]);

  const flat = useMemo(
    () => sections.flatMap((section) => section.items),
    [sections],
  );

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(
      `[data-index="${active}"]`,
    );
    el?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;

  const select = (index: number) => {
    const item = flat[index];
    if (item) onPick(item.manifest);
  };

  const heading =
    pending?.kind === "insert"
      ? "Вставить шаг"
      : tab === "triggers"
        ? "Добавить триггер"
        : "Добавить шаг";

  const hint =
    pending?.kind === "insert"
      ? "Шаг встанет между двумя связанными узлами"
      : pending?.kind === "output" && context
        ? `После «${context.label}»${
            context.handle && context.handle !== "out"
              ? ` · ветка «${handleLabel(context.handle)}»`
              : ""
          }`
        : context
          ? `Соединится с «${context.label}»`
          : "Шаг появится на холсте без связей";

  return (
    <aside className="auto-node-picker" role="dialog" aria-label="Добавить шаг">
      <div className="auto-node-picker-head">
        <div className="auto-node-picker-headline">
          <div>
            <h2>{heading}</h2>
            <p>{hint}</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Закрыть"
            onClick={onClose}
          >
            <X size={16} />
          </Button>
        </div>
        <label className="auto-node-picker-search">
          <Search size={15} aria-hidden />
          <input
            ref={inputRef}
            aria-label="Поиск шагов"
            placeholder="Что должно произойти?"
            value={search}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => {
              setSearch(event.target.value);
              setActive(0);
            }}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActive((value) => Math.min(value + 1, flat.length - 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive((value) => Math.max(value - 1, 0));
              } else if (event.key === "Enter") {
                event.preventDefault();
                select(active);
              } else if (event.key === "Escape") {
                event.preventDefault();
                onClose();
              } else if (event.key === "Tab" && !event.shiftKey) {
                event.preventDefault();
                setTab((value) => (value === "steps" ? "triggers" : "steps"));
                setActive(0);
              }
            }}
          />
          <kbd aria-hidden>
            <CornerDownLeft size={11} />
          </kbd>
        </label>
        <div className="auto-node-picker-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "steps"}
            className={tab === "steps" ? "active" : undefined}
            onClick={() => {
              setTab("steps");
              setActive(0);
            }}
          >
            Шаги
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "triggers"}
            className={tab === "triggers" ? "active" : undefined}
            onClick={() => {
              setTab("triggers");
              setActive(0);
            }}
          >
            Триггеры
          </button>
        </div>
      </div>

      <div className="auto-node-picker-body" ref={listRef}>
        {sections.map((section) => (
          <section key={section.key}>
            <h3>{section.title}</h3>
            {section.items.map((item) => {
              const index = flat.indexOf(item);
              const Icon = item.entry.icon;
              const risk = riskOf(item.manifest);
              return (
                <button
                  key={`${section.key}-${item.manifest.type}`}
                  type="button"
                  data-index={index}
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.setData(
                      PALETTE_MIME,
                      item.manifest.type,
                    );
                    event.dataTransfer.effectAllowed = "copy";
                  }}
                  className={`auto-node-picker-item${index === active ? " active" : ""}`}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => onPick(item.manifest)}
                >
                  <span
                    className={`auto-node-picker-icon auto-step-${item.entry.group}`}
                    aria-hidden
                  >
                    <Icon size={17} strokeWidth={1.9} />
                  </span>
                  <span className="auto-node-picker-text">
                    <strong>{item.entry.title}</strong>
                    <small>{item.entry.description}</small>
                  </span>
                  <em className={`auto-node-picker-risk risk-${risk.tone}`}>
                    {risk.text}
                  </em>
                </button>
              );
            })}
          </section>
        ))}
        {!flat.length && (
          <div className="auto-node-picker-empty">
            <p>Ничего не нашлось по запросу «{search}».</p>
            {tab === "steps" ? (
              <button
                type="button"
                className="auto-link"
                onClick={() => {
                  setTab("triggers");
                  setActive(0);
                }}
              >
                Искать среди триггеров
              </button>
            ) : (
              <button
                type="button"
                className="auto-link"
                onClick={() => {
                  setTab("steps");
                  setActive(0);
                }}
              >
                Искать среди шагов
              </button>
            )}
          </div>
        )}
      </div>
      <div className="auto-node-picker-foot">
        <span>
          <kbd>↑</kbd>
          <kbd>↓</kbd> выбор
        </span>
        <span>
          <kbd>Enter</kbd> добавить
        </span>
        <span>
          <kbd>Esc</kbd> закрыть
        </span>
      </div>
    </aside>
  );
}
