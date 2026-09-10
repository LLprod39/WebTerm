import { Link } from "react-router-dom";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import {
  ArrowLeft,
  Copy,
  Download,
  History,
  LayoutDashboard,
  MoreHorizontal,
  Play,
  Plus,
  Save,
  Settings2,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui";

export function EditorTopBar({
  name,
  dirty,
  canRuns,
  pipelineId,
  layoutHint,
  savePending,
  stepCount,
  onName,
  onSave,
  onRun,
  onAddStep,
  onProcessSettings,
  onLayout,
  onDownload,
  onClone,
  onDelete,
}: {
  name: string;
  dirty: boolean;
  canRuns: boolean;
  pipelineId: number;
  layoutHint: boolean;
  savePending: boolean;
  stepCount: number;
  onName: (value: string) => void;
  onSave: () => void;
  onRun: () => void;
  onAddStep: () => void;
  onProcessSettings: () => void;
  onLayout: () => void;
  onDownload: () => void;
  onClone: () => void;
  onDelete: () => void;
}) {
  const canSave = dirty && name.trim().length > 0;
  return (
    <header className="auto-editor-topbar">
      <div className="auto-editor-topbar-left">
        <Link
          className="btn btn-ghost btn-icon"
          to="/automation/pipelines"
          aria-label="К процессам"
        >
          <ArrowLeft size={16} />
        </Link>
        <div className="auto-editor-title">
          <input
            className="auto-editor-name"
            aria-label="Название процесса"
            value={name}
            placeholder="Название процесса"
            onChange={(event) => onName(event.target.value)}
          />
          <span
            className={`auto-editor-state${dirty ? " dirty" : ""}`}
            role="status"
          >
            <span className="auto-editor-state-dot" aria-hidden />
            {savePending
              ? "Сохранение…"
              : dirty
                ? "Не сохранено"
                : "Сохранено"}
            {!savePending && stepCount > 0 && (
              <span className="auto-editor-state-sep">
                · {stepCount} {stepCount === 1 ? "шаг" : stepCount < 5 ? "шага" : "шагов"}
              </span>
            )}
          </span>
        </div>
        {layoutHint && (
          <Button size="sm" variant="ghost" onClick={onLayout}>
            <LayoutDashboard size={13} />
            Разложить слева направо
          </Button>
        )}
      </div>
      <div className="auto-editor-topbar-right">
        <Button variant="ghost" onClick={onAddStep} title="Tab">
          <Plus size={15} />
          Добавить шаг
        </Button>
        <Button
          variant={canSave ? "primary" : "secondary"}
          loading={savePending}
          disabled={!canSave}
          onClick={onSave}
          title="Ctrl+S"
        >
          <Save size={14} />
          Сохранить
        </Button>
        <Button
          variant={dirty ? "secondary" : "primary"}
          disabled={dirty}
          onClick={onRun}
          title={dirty ? "Сначала сохраните процесс" : undefined}
        >
          <Play size={14} />
          Проверить и запустить
        </Button>
        <Dropdown.Root>
          <Dropdown.Trigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Дополнительные действия"
            >
              <MoreHorizontal size={16} />
            </Button>
          </Dropdown.Trigger>
          <Dropdown.Portal>
            <Dropdown.Content
              className="menu-content"
              align="end"
              sideOffset={8}
            >
              <Dropdown.Item
                className="menu-item"
                onSelect={onProcessSettings}
              >
                <Settings2 size={14} />
                Название и описание
              </Dropdown.Item>
              <Dropdown.Item className="menu-item" onSelect={onLayout}>
                <LayoutDashboard size={14} />
                Разложить поток
              </Dropdown.Item>
              {canRuns && (
                <Dropdown.Item asChild className="menu-item">
                  <Link to={`/automation/runs?pipeline=${pipelineId}`}>
                    <History size={14} />
                    История запусков
                  </Link>
                </Dropdown.Item>
              )}
              <Dropdown.Separator className="menu-separator" />
              <Dropdown.Item className="menu-item" onSelect={onDownload}>
                <Download size={14} />
                Скачать JSON
              </Dropdown.Item>
              <Dropdown.Item className="menu-item" onSelect={onClone}>
                <Copy size={14} />
                Дублировать процесс
              </Dropdown.Item>
              <Dropdown.Item
                className="menu-item danger"
                onSelect={onDelete}
              >
                <Trash2 size={14} />
                Удалить процесс
              </Dropdown.Item>
            </Dropdown.Content>
          </Dropdown.Portal>
        </Dropdown.Root>
      </div>
    </header>
  );
}
