import { statusClasses, statusLabel } from "./formatters";

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${statusClasses(status)}`}
    >
      {statusLabel(status)}
    </span>
  );
}
