import { useEffect, useMemo, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import type { NodeManifest } from "@/api/automation";
import { Button } from "@/components/ui";
import {
  GROUP_LABELS,
  resolveCatalog,
  type NodeGroup,
} from "./catalog";

export type PickerPending =
  | { kind: "output"; source: string; handle: string }
  | { kind: "insert"; edgeId: string }
  | { kind: "position"; x: number; y: number }
  | { kind: "free" }
  | null;

const TRIGGER_GROUPS = new Set<NodeGroup>(["trigger"]);

export function NodePicker({
  open,
  manifests,
  pending,
  onClose,
  onPick,
}: {
  open: boolean;
  manifests: NodeManifest[];
  pending: PickerPending;
  onClose: () => void;
  onPick: (manifest: NodeManifest) => void;
}) {
  const preferTriggers =
    pending?.kind === "free" &&
    !manifests.some((m) => !m.type.startsWith("trigger/"));
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<"triggers" | "steps">(
    preferTriggers ? "triggers" : "steps",
  );
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);

  const items = useMemo(() => {
    const query = search.trim().toLowerCase();
    return manifests
      .map((manifest) => ({
        manifest,
        entry: resolveCatalog(manifest.type, manifest),
      }))
      .filter(({ entry, manifest }) => {
        const isTrigger = TRIGGER_GROUPS.has(entry.group);
        if (tab === "triggers" ? !isTrigger : isTrigger) return false;
        if (!query) return true;
        return `${entry.title} ${entry.description} ${manifest.type} ${manifest.category} ${manifest.tags.join(" ")}`
          .toLowerCase()
          .includes(query);
      });
  }, [manifests, search, tab]);

  const grouped = useMemo(() => {
    const map = new Map<NodeGroup, typeof items>();
    for (const item of items) {
      const list = map.get(item.entry.group) ?? [];
      list.push(item);
      map.set(item.entry.group, list);
    }
    return [...map.entries()];
  }, [items]);

  if (!open) return null;

  const flat = items;
  const select = (index: number) => {
    const item = flat[index];
    if (item) onPick(item.manifest);
  };

  return (
    <aside
      className="auto-node-picker"
      role="dialog"
      aria-label="Добавить шаг"
    >
      <div className="auto-node-picker-head">
        <div className="auto-toolbar">
          <h2>Добавить шаг</h2>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Закрыть"
            onClick={onClose}
          >
            <X size={16} />
          </Button>
        </div>
        <p>
          {pending?.kind === "insert"
            ? "Выберите шаг для вставки в связь"
            : pending?.kind === "output"
              ? "Шаг будет соединён с выбранным выходом"
              : "Поиск или выбор шага для потока слева направо"}
        </p>
        <label className="auto-node-picker-search">
          <Search size={14} aria-hidden />
          <input
            ref={inputRef}
            aria-label="Поиск шагов"
            placeholder="Найти шаг…"
            value={search}
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
              }
            }}
          />
        </label>
        <div className="auto-node-picker-tabs" role="tablist">
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
        </div>
      </div>
      <div className="auto-node-picker-body">
        {grouped.map(([group, groupItems]) => (
          <section key={group}>
            <h3>{GROUP_LABELS[group]}</h3>
            {groupItems.map((item) => {
              const index = flat.indexOf(item);
              const Icon = item.entry.icon;
              return (
                <button
                  key={item.manifest.type}
                  type="button"
                  className={`auto-node-picker-item${index === active ? " active" : ""}`}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => onPick(item.manifest)}
                >
                  <span
                    className={`auto-node-picker-icon auto-step-${item.entry.group}`}
                    aria-hidden
                  >
                    <Icon size={18} />
                  </span>
                  <span>
                    <strong>{item.entry.title}</strong>
                    <small>{item.entry.description}</small>
                    <span className="auto-node-picker-meta">
                      {item.manifest.requires_approval_by_default && (
                        <em>согласование</em>
                      )}
                      {item.manifest.mutates_state && <em>изменяет</em>}
                      {!item.manifest.mutates_state &&
                        !item.manifest.requires_approval_by_default && (
                          <em>только чтение</em>
                        )}
                    </span>
                  </span>
                </button>
              );
            })}
          </section>
        ))}
        {!flat.length && (
          <p className="auto-empty-note">Нет шагов по этому запросу.</p>
        )}
      </div>
    </aside>
  );
}
