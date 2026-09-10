import { createContext, useContext, useEffect, type ReactNode } from "react";
import {
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { authApi, type Session, type SessionUser } from "@/api/auth";
export async function replaceSession(client: QueryClient, session: Session) {
  await client.cancelQueries();
  client.removeQueries({
    predicate: (query) => query.queryKey[0] !== "session",
  });
  client.setQueryData(["session"], session);
}
const Context = createContext<{
  user: SessionUser | null;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
}>({ user: null, loading: true, error: null, refresh: () => {} });
export function SessionProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["session"],
    queryFn: ({ signal }) => authApi.session(signal),
    retry: false,
    staleTime: 60_000,
  });
  useEffect(() => {
    const expire = () => {
      void replaceSession(client, { authenticated: false, user: null });
    };
    window.addEventListener("webterm:session-expired", expire);
    return () => window.removeEventListener("webterm:session-expired", expire);
  }, [client]);
  return (
    <Context.Provider
      value={{
        user: query.data?.user ?? null,
        loading: query.isPending,
        error: query.error,
        refresh: () => {
          void client.invalidateQueries({ queryKey: ["session"] });
        },
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useSession() {
  return useContext(Context);
}
export function usePermission(feature?: string) {
  const { user } = useSession();
  return !!user && (!feature || user.features[feature] === true);
}
