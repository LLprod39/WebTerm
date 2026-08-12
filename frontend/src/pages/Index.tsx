import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchAuthSession } from "@/lib/api";
import { firstAllowedApplicationPath } from "@/lib/navigation";
import { localize, useI18n } from "@/lib/i18n";

const Index = () => {
  const navigate = useNavigate();
  const { lang } = useI18n();
  const { data } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    if (data?.authenticated) {
      const destination = firstAllowedApplicationPath(data.user);
      if (destination) navigate(destination, { replace: true });
    }
  }, [data, navigate]);

  if (data?.authenticated && !firstAllowedApplicationPath(data.user)) {
    return (
      <section className="mx-auto mt-12 max-w-lg rounded-xl border border-border bg-card p-6 text-center">
        <h1 className="text-xl font-semibold text-foreground">
          {localize(lang, "Нет доступных разделов", "No available sections")}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {localize(
            lang,
            "Попросите администратора назначить пилотный профиль доступа.",
            "Ask an administrator to assign a pilot access profile.",
          )}
        </p>
      </section>
    );
  }

  return null;
};

export default Index;
