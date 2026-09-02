import * as Dropdown from "@radix-ui/react-dropdown-menu";

export type ContextTarget =
  | { kind: "node"; id: string }
  | { kind: "edge"; id: string }
  | { kind: "pane"; x: number; y: number }
  | null;

export function ContextMenu({
  open,
  x,
  y,
  target,
  onOpenChange,
  onConfigure,
  onDuplicate,
  onDeleteNode,
  onInsert,
  onDeleteEdge,
  onAddHere,
  onLayout,
  onSelectAll,
  onPaste,
  canPaste,
}: {
  open: boolean;
  x: number;
  y: number;
  target: ContextTarget;
  onOpenChange: (open: boolean) => void;
  onConfigure: (id: string) => void;
  onDuplicate: (id: string) => void;
  onDeleteNode: (id: string) => void;
  onInsert: (edgeId: string) => void;
  onDeleteEdge: (edgeId: string) => void;
  onAddHere: (x: number, y: number) => void;
  onLayout: () => void;
  onSelectAll: () => void;
  onPaste: () => void;
  canPaste: boolean;
}) {
  if (!target) return null;

  return (
    <Dropdown.Root open={open} onOpenChange={onOpenChange}>
      <Dropdown.Portal>
        <Dropdown.Content
          className="menu-content auto-context-menu"
          style={{ position: "fixed", left: x, top: y }}
          sideOffset={0}
          align="start"
        >
          {target.kind === "node" && (
            <>
              <Dropdown.Item
                className="menu-item"
                onSelect={() => onConfigure(target.id)}
              >
                Настроить
              </Dropdown.Item>
              <Dropdown.Item
                className="menu-item"
                onSelect={() => onDuplicate(target.id)}
              >
                Дублировать
              </Dropdown.Item>
              <Dropdown.Item
                className="menu-item"
                onSelect={() => onDeleteNode(target.id)}
              >
                Удалить
              </Dropdown.Item>
            </>
          )}
          {target.kind === "edge" && (
            <>
              <Dropdown.Item
                className="menu-item"
                onSelect={() => onInsert(target.id)}
              >
                Вставить шаг
              </Dropdown.Item>
              <Dropdown.Item
                className="menu-item"
                onSelect={() => onDeleteEdge(target.id)}
              >
                Удалить связь
              </Dropdown.Item>
            </>
          )}
          {target.kind === "pane" && (
            <>
              <Dropdown.Item
                className="menu-item"
                onSelect={() => onAddHere(target.x, target.y)}
              >
                Добавить шаг здесь
              </Dropdown.Item>
              <Dropdown.Item className="menu-item" onSelect={onLayout}>
                Разложить
              </Dropdown.Item>
              <Dropdown.Item className="menu-item" onSelect={onSelectAll}>
                Выделить всё
              </Dropdown.Item>
              <Dropdown.Item
                className="menu-item"
                disabled={!canPaste}
                onSelect={onPaste}
              >
                Вставить
              </Dropdown.Item>
            </>
          )}
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}
