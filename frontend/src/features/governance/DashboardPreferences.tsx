import { Fragment, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  dashboardLayoutApi,
  readOverviewLayout,
  type DashboardSectionId,
  type DashboardType,
} from "@/api/dashboard-layout";
import { useSession } from "@/app/session";
import { EmptyState, ErrorState } from "@/components/ui";
import "./dashboard-preferences.css";

export function useDashboardLayout() {
  const { user } = useSession();
  const type: DashboardType = user?.is_staff ? "admin" : "user";
  const queryKey = ["dashboard-layout", user?.id, type] as const;
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => dashboardLayoutApi.get(type, signal),
    enabled: !!user,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
  return {
    ...query,
    layout: readOverviewLayout(query.data?.layout),
    type,
    queryKey,
  };
}

export function DashboardSections({
  sections,
}: {
  sections: Record<DashboardSectionId, ReactNode>;
}) {
  const query = useDashboardLayout();
  const visible = (column: "main" | "side") =>
    query.layout.columns[column].filter(
      (id) => !query.layout.hidden.includes(id),
    );
  const main = visible("main");
  const side = visible("side");
  return (
    <>
      {query.error && (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      )}
      {!main.length && !side.length ? (
        <EmptyState
          title="Виджеты обзора скрыты"
          description="Выберите нужные виджеты в персональных настройках."
          action={
            <Link className="btn btn-secondary" to="/settings/workspace">
              Настроить обзор
            </Link>
          }
        />
      ) : (
        <div
          className={`dashboard-sections${!main.length || !side.length ? " dashboard-sections-single" : ""}`}
        >
          {[main, side]
            .filter((ids) => ids.length > 0)
            .map((ids, index) => (
              <div className="stack" key={index}>
                {ids.map((id) => (
                  <Fragment key={id}>{sections[id]}</Fragment>
                ))}
              </div>
            ))}
        </div>
      )}
    </>
  );
}
