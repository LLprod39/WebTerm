import {
  useId,
  useMemo,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Check,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Loader2,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { cn, errorMessage } from "@/lib/utils";
export function Button({
  variant = "secondary",
  size = "md",
  loading,
  className,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "icon";
  loading?: boolean;
}) {
  return (
    <button
      type="button"
      className={cn("btn", `btn-${variant}`, `btn-${size}`, className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 size={15} className="spin" />}
      {children}
    </button>
  );
}
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <div className="page-description">{description}</div>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}
export function Panel({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("panel", className)}>
      {(title || actions) && (
        <div className="panel-header">
          <div>
            <h2>{title}</h2>
            {description && <p className="muted text-sm">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}
const labels: Record<string, string> = {
  healthy: "В норме",
  online: "Подключён",
  connected: "Подключено",
  success: "Успешно",
  succeeded: "Успешно",
  completed: "Завершено",
  active: "Активен",
  ready: "Готов",
  warning: "Внимание",
  critical: "Критично",
  failed: "Ошибка",
  error: "Ошибка",
  offline: "Не в сети",
  unreachable: "Недоступен",
  unknown: "Нет данных",
  running: "Выполняется",
  pending: "Ожидание",
  queued: "В очереди",
  cancelled: "Отменён",
  disabled: "Отключено",
  draft: "Черновик",
  connecting: "Подключение",
  reconnecting: "Переподключение",
  disconnected: "Отключено",
  stale: "Устарело",
  partial: "Частично",
  approved: "Одобрено",
  blocked: "Заблокировано",
  waiting_for_input: "Нужен ответ",
};
export function StatusBadge({
  status,
  children,
}: {
  status: string;
  children?: ReactNode;
}) {
  const tone =
    /^(healthy|online|connected|success|succeeded|completed|active|ready|approved)$/.test(
      status,
    )
      ? "success"
      : /^(failed|error|critical|unreachable|blocked)$/.test(status)
        ? "danger"
        : /^(warning|stale|partial|waiting_for_input)$/.test(status)
          ? "warning"
          : /^(running|connecting|reconnecting)$/.test(status)
            ? "info"
            : "neutral";
  return (
    <span className={cn("status", `status-${tone}`)}>
      <span className="status-dot" />
      {children ?? labels[status] ?? status}
    </span>
  );
}
export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">{icon ?? <Inbox size={24} />}</span>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div role="alert" className="error-state">
      <AlertCircle size={20} />
      <div>
        <strong>Не удалось загрузить данные</strong>
        <p>{errorMessage(error)}</p>
      </div>
      {retry && (
        <Button onClick={retry}>
          <RefreshCw size={14} />
          Повторить
        </Button>
      )}
    </div>
  );
}
export function Feedback({
  error,
  success,
}: {
  error?: unknown;
  success?: string;
}) {
  return (
    <>
      {error ? (
        <div role="alert" className="notice notice-danger">
          <AlertCircle size={16} />
          {errorMessage(error)}
        </div>
      ) : null}
      {success && (
        <div role="status" className="notice notice-success">
          <Check size={16} />
          {success}
        </div>
      )}
    </>
  );
}
export function LoadingState({
  label = "Загрузка данных…",
}: {
  label?: string;
}) {
  return (
    <div className="loading-state" role="status">
      <Loader2 className="spin" size={20} />
      <span>{label}</span>
    </div>
  );
}
export function Skeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="skeleton-list" role="status" aria-label="Загрузка">
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton" key={i} />
      ))}
    </div>
  );
}
export function Field({
  label,
  description,
  error,
  children,
  htmlFor,
}: {
  label: string;
  description?: string;
  error?: string;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {description && <small>{description}</small>}
      {error && (
        <small className="field-error" role="alert">
          {error}
        </small>
      )}
    </div>
  );
}
export function Drawer({
  open,
  onOpenChange,
  closeDisabled = false,
  onCloseAutoFocus,
  title,
  description,
  children,
  footer,
  wide = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  closeDisabled?: boolean;
  onCloseAutoFocus?: (event: Event) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content
          className={cn("drawer", wide && "drawer-wide")}
          onCloseAutoFocus={onCloseAutoFocus}
          aria-describedby={description ? undefined : undefined}
        >
          <div className="drawer-header">
            <div>
              <Dialog.Title>{title}</Dialog.Title>
              {description ? (
                <Dialog.Description>{description}</Dialog.Description>
              ) : (
                <Dialog.Description className="sr-only">
                  {title}
                </Dialog.Description>
              )}
            </div>
            <Dialog.Close asChild>
              <Button
                size="icon"
                variant="ghost"
                aria-label="Закрыть"
                disabled={closeDisabled}
              >
                <X size={19} />
              </Button>
            </Dialog.Close>
          </div>
          <div className="drawer-body">{children}</div>
          {footer && <div className="drawer-footer">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  onConfirm,
  pending = false,
  confirmLabel = "Подтвердить",
  typedText,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  onConfirm: () => void;
  pending?: boolean;
  confirmLabel?: string;
  typedText?: string;
}) {
  const [text, setText] = useState("");
  const id = useId();
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(value) => {
        if (pending) return;
        setText("");
        onOpenChange(value);
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="confirm-dialog">
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description asChild>
            <div className="muted">{description}</div>
          </Dialog.Description>
          {typedText && (
            <Field label={`Введите «${typedText}»`} htmlFor={id}>
              <input
                id={id}
                value={text}
                disabled={pending}
                autoComplete="off"
                onChange={(e) => setText(e.target.value)}
              />
            </Field>
          )}
          <div className="dialog-actions">
            <Button disabled={pending} onClick={() => onOpenChange(false)}>
              Отмена
            </Button>
            <Button
              variant="danger"
              loading={pending}
              disabled={!!typedText && text !== typedText}
              onClick={onConfirm}
            >
              {confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export interface Column<T> {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number;
  className?: string;
}
export function DataTable<T>({
  rows,
  columns,
  rowKey,
  searchValue,
  searchPlaceholder = "Поиск…",
  emptyTitle = "Пока ничего нет",
  emptyDescription,
  emptyAction,
  onRowClick,
  toolbar,
  pageSize = 15,
  hideSinglePagePagination = false,
  defaultSort = null,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string | number;
  searchValue?: (row: T) => string;
  searchPlaceholder?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
  onRowClick?: (row: T) => void;
  toolbar?: ReactNode;
  pageSize?: number;
  hideSinglePagePagination?: boolean;
  defaultSort?: { key: string; desc: boolean } | null;
}) {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ key: string; desc: boolean } | null>(defaultSort);
  const [page, setPage] = useState(0);
  const filtered = useMemo(() => {
    const found = rows.filter(
      (row) =>
        !searchValue ||
        searchValue(row)
          .toLocaleLowerCase()
          .includes(search.toLocaleLowerCase()),
    );
    const col = columns.find((c) => c.key === sort?.key);
    if (col?.sortValue)
      found.sort((a, b) => {
        const av = col.sortValue!(a),
          bv = col.sortValue!(b);
        return (
          (typeof av === "number" && typeof bv === "number"
            ? av - bv
            : String(av).localeCompare(String(bv), "ru")) *
          (sort?.desc ? -1 : 1)
        );
      });
    return found;
  }, [rows, columns, sort, search, searchValue]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const current = Math.min(page, pages - 1);
  const visible = filtered.slice(current * pageSize, (current + 1) * pageSize);
  return (
    <div className="data-view">
      {(searchValue || toolbar) && (
        <div className="table-toolbar">
          {searchValue && (
            <div className="search-field">
              <Search size={16} />
              <input
                aria-label={searchPlaceholder}
                placeholder={searchPlaceholder}
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(0);
                }}
              />
              {search && (
                <button
                  aria-label="Очистить поиск"
                  onClick={() => setSearch("")}
                >
                  <X size={14} />
                </button>
              )}
            </div>
          )}
          {toolbar}
        </div>
      )}
      {!filtered.length ? (
        <EmptyState
          title={search ? "Ничего не найдено" : emptyTitle}
          description={
            search ? "Измените поисковый запрос или фильтры." : emptyDescription
          }
          action={!search ? emptyAction : undefined}
        />
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th
                      key={col.key}
                      className={col.className}
                      aria-sort={
                        sort?.key === col.key
                          ? sort.desc
                            ? "descending"
                            : "ascending"
                          : undefined
                      }
                    >
                      {col.sortValue ? (
                        <button
                          className="sort-button"
                          onClick={() =>
                            setSort({
                              key: col.key,
                              desc: sort?.key === col.key ? !sort.desc : false,
                            })
                          }
                        >
                          {col.label}
                          {sort?.key === col.key ? (
                            sort.desc ? (
                              <ArrowDown size={12} />
                            ) : (
                              <ArrowUp size={12} />
                            )
                          ) : null}
                        </button>
                      ) : (
                        col.label
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr
                    key={rowKey(row)}
                    className={onRowClick ? "clickable-row" : ""}
                    onClick={() => onRowClick?.(row)}
                  >
                    {columns.map((col) => (
                      <td key={col.key} className={col.className}>
                        {col.render(row)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(!hideSinglePagePagination || pages > 1) && (
            <div className="table-footer">
              <span>
                {current * pageSize + 1}–
                {Math.min((current + 1) * pageSize, filtered.length)} из{" "}
                {filtered.length}
              </span>
              <div>
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="Предыдущая страница"
                  disabled={current === 0}
                  onClick={() => setPage(current - 1)}
                >
                  <ChevronLeft size={16} />
                </Button>
                <span>
                  {current + 1} / {pages}
                </span>
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="Следующая страница"
                  disabled={current === pages - 1}
                  onClick={() => setPage(current + 1)}
                >
                  <ChevronRight size={16} />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
export function Metric({
  label,
  value,
  detail,
  icon,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="metric">
      <div className="metric-label">
        {label}
        {icon}
      </div>
      <div className="metric-value">{value}</div>
      {detail && <div className="metric-detail">{detail}</div>}
    </div>
  );
}
export function JsonDetails({
  data,
  label = "Технические детали",
}: {
  data: unknown;
  label?: string;
}) {
  return (
    <details className="technical-details">
      <summary>{label}</summary>
      <pre className="code-block">{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}
export function Tabs({
  items,
  value,
  onChange,
  disabled = false,
}: {
  items: { value: string; label: string; count?: number }[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="tabs" role="tablist">
      {items.map((item, index) => (
        <button
          type="button"
          key={item.value}
          role="tab"
          disabled={disabled}
          tabIndex={value === item.value ? 0 : -1}
          aria-selected={value === item.value}
          className={value === item.value ? "active" : ""}
          onClick={() => onChange(item.value)}
          onKeyDown={(event) => {
            const nextIndex =
              event.key === "ArrowRight"
                ? (index + 1) % items.length
                : event.key === "ArrowLeft"
                  ? (index + items.length - 1) % items.length
                  : event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? items.length - 1
                      : -1;
            if (nextIndex < 0) return;
            event.preventDefault();
            onChange(items[nextIndex].value);
            const buttons =
              event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
                '[role="tab"]',
              );
            buttons?.[nextIndex]?.focus();
          }}
        >
          {item.label}
          {item.count != null && <span>{item.count}</span>}
        </button>
      ))}
    </div>
  );
}
