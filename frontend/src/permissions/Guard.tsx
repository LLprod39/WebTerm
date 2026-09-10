import type { ReactNode } from "react";
import { useSession } from "@/app/session";
import { EmptyState } from "@/components/ui";
export function Guard({
  feature,
  staff,
  children,
}: {
  feature?: string;
  staff?: boolean;
  children: ReactNode;
}) {
  const { user } = useSession();
  if (
    !user ||
    (feature && !user.features[feature]) ||
    (staff && !user.is_staff)
  )
    return (
      <EmptyState
        title="Доступ ограничен"
        description="Вашей роли недоступен этот раздел. Обратитесь к администратору рабочего пространства."
      />
    );
  return children;
}
