import { useQuery } from "@tanstack/react-query";
import { fetchAuthSession } from "@/lib/api";
import UserDashboard from "./UserDashboard";
import AdminDashboard from "./AdminDashboard";

export default function DashboardRouter() {
  const { data, isLoading } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading...</div>;
  }

  if (data?.user?.is_staff) {
    return <AdminDashboard />;
  }

  return <UserDashboard />;
}
