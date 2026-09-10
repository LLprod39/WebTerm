import { Navigate } from "react-router-dom";
import { useSession } from "@/app/session";
import { EmptyState } from "@/components/ui";
import { sectionLanding, visibleNavigation } from "./navigation";

export function NavigationLanding({
  section,
  parentPath,
}: {
  section: string;
  parentPath?: string;
}) {
  const { user } = useSession();
  const group = visibleNavigation(user).find((item) => item.id === section);
  const destination =
    group &&
    (parentPath
      ? group.items.find((item) => item.parentPath === parentPath)
      : sectionLanding(group));
  return destination ? (
    <Navigate to={destination.path} replace />
  ) : (
    <EmptyState
      title="Недостаточно прав"
      description="Доступ к этому разделу предоставляется администратором."
    />
  );
}
