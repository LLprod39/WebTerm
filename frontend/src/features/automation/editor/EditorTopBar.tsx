import { Link } from "react-router-dom";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import {
  ArrowLeft,
  Copy,
  Download,
  LayoutDashboard,
  MoreHorizontal,
  Play,
  Plus,
  Save,
  Settings2,
  Trash2,
} from "lucide-react";
import { Button, StatusBadge } from "@/components/ui";

export function EditorTopBar({
  name,
  dirty,
  canRuns,
  pipelineId,
  layoutHint,
  savePending,
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
        <input
          className="auto-editor-name"
          aria-label="Название процесса"
          value={name}
          onChange={(event) => onName(event.target.value)}
        />
        <StatusBadge status={dirty ? "draft" : "success"}>
          {dirty ? "Не сохранено" : "Сохранено"}
        </StatusBadge>
        {layoutHint && (
          <Button size="sm" variant="ghost" onClick={onLayout}>
            <LayoutDashboard size={13} />
            Разложить слева направо
          </Button>
        )}
      </div>
      <div className="auto-editor-topbar-right">
        <Button onClick={onAddStep}>
          <Plus size={15} />
          Добавить шаг
        </Button>
        <Button variant="ghost" onClick={onProcessSettings}>
          <Settings2 size={14} />
          Свойства процесса
        </Button>
        <Button
          loading={savePending}
          disabled={!dirty || !name.trim()}
          onClick={onSave}
        >
          <Save size={14} />
          Сохранить
        </Button>
        <Button variant="primary" disabled={dirty} onClick={onRun}>
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
            <Dropdown.Content className="menu-content" align="end" sideOffset={8}>
              {canRuns && (
                <Dropdown.Item asChild className="menu-item">
                  <Link to={`/automation/runs?pipeline=${pipelineId}`}>
                    Запуски
                  </Link>
                </Dropdown.Item>
              )}
              <Dropdown.Item className="menu-item" onSelect={onDownload}>
                <Download size={14} />
                Скачать JSON
              </Dropdown.Item>
              <Dropdown.Item className="menu-item" onSelect={onClone}>
                <Copy size={14} />
                Дублировать процесс
              </Dropdown.Item>
              <Dropdown.Item className="menu-item" onSelect={onDelete}>
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
