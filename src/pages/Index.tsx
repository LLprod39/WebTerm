import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchAuthSession } from "@/lib/api";

const Index = () => {
  const navigate = useNavigate();
  const { data } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    if (data) {
      navigate("/dashboard", { replace: true });
    }
  }, [data, navigate]);

  return null;
};

export default Index;
