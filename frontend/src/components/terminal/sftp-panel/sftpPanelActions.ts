import type { SftpEntry } from "@/lib/api";
import { defaultPermissionMode } from "./sftpPanelModel";


export type SftpFormAction =
  | { type: "create-folder"; value: string; error?: string }
  | { type: "create-file"; value: string; error?: string }
  | { type: "rename"; value: string; entry: SftpEntry; error?: string }
  | { type: "chmod"; value: string; entry: SftpEntry; error?: string }
  | { type: "chown"; value: string; entry: SftpEntry; error?: string };

export type PendingEditorAction =
  | { type: "open"; entry: SftpEntry }
  | { type: "reload" }
  | { type: "close" };

export function formActionCopy(action: SftpFormAction | null) {
  if (!action) return null;
  switch (action.type) {
    case "create-folder":
      return {
        title: "Новая папка",
        description: "Папка будет создана в текущем каталоге.",
        label: "Имя папки",
        placeholder: "logs",
        confirmLabel: "Создать папку",
      };
    case "create-file":
      return {
        title: "Новый файл",
        description: "Пустой файл будет создан и открыт в редакторе.",
        label: "Имя файла",
        placeholder: "new-file.conf",
        confirmLabel: "Создать файл",
      };
    case "rename":
      return {
        title: "Переименовать объект",
        description: `Текущее имя: ${action.entry.name}`,
        label: "Новое имя",
        placeholder: action.entry.name,
        confirmLabel: "Переименовать",
      };
    case "chmod":
      return {
        title: "Изменить права доступа",
        description: `Права будут применены к ${action.entry.name}. Используйте формат 644, 755 или 0644.`,
        label: "Права",
        placeholder: defaultPermissionMode(action.entry),
        confirmLabel: "Обновить права",
      };
    case "chown":
      return {
        title: "Изменить владельца",
        description: `Владелец будет обновлён для ${action.entry.name}. Можно указать owner или owner:group.`,
        label: "Владелец",
        placeholder: "deploy:www-data",
        confirmLabel: "Обновить владельца",
      };
  }
}
