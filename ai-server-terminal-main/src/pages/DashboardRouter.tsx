import { useQuery } from "@tanstack/react-query";
import { fetchAuthSession } from "@/lib/api";
import UserDashboard from "./UserDashboard";
import AdminDashboard from "./AdminDashboard";
import { QueryStateBlock } from "@/components/ui/page-shell";

export default function DashboardRouter() {
  const { data, isLoading } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });

  if (isLoading) {
    return <QueryStateBlock loading className="p-6">{null}</QueryStateBlock>;
  }

  if (data?.user?.is_staff) {
    return <AdminDashboard />;
  }

  return <UserDashboard />;
}
