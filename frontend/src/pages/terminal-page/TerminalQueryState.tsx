import { QueryStateBlock } from "@/components/ui/page-shell";

export function TerminalQueryState({
  isLoading,
  error,
  hasData,
  hasActiveConnection,
}: {
  isLoading: boolean;
  error: Error | null;
  hasData: boolean;
  hasActiveConnection: boolean;
}) {
  return (
    <QueryStateBlock
      loading={isLoading}
      error={
        error
          ? error
          : !isLoading && !hasData
            ? new Error("Ошибка загрузки данных терминала")
            : !hasActiveConnection
              ? new Error("Сервер не найден или недоступен")
              : undefined
      }
      className="p-6"
    >
      {null}
    </QueryStateBlock>
  );
}
