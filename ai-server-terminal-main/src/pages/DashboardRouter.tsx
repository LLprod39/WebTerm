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
    return <div className="w-full px-4 py-5 text-sm text-muted-foreground md:px-6 xl:px-8">Loading...</div>;
  }

  if (data?.user?.is_staff) {
    return <AdminDashboard />;
  }

  return <UserDashboard />;
}
