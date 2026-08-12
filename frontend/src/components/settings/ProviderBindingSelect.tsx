import { useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchAiProviderConnections,
  fetchAiProviderPools,
  aiProviderQueryKeys,
  type ProviderBinding,
} from "@/api/aiProviders";
import type { AuthSessionResponse } from "@/api/auth";
import { hasFeatureAccess } from "@/lib/featureAccess";
import { localize } from "@/lib/i18n";

type ProviderBindingSelectProps = {
  value?: ProviderBinding | null;
  onChange: (binding: ProviderBinding | null) => void;
  mode: "interactive" | "unattended";
  lang: "ru" | "en";
  disabled?: boolean;
  className?: string;
  ariaLabel?: string;
};

function bindingValue(binding?: ProviderBinding | null) {
  if (binding?.connection_id) return `connection:${binding.connection_id}`;
  if (binding?.pool_id) return `pool:${binding.pool_id}`;
  return "";
}

export function ProviderBindingSelect({
  value,
  onChange,
  mode,
  lang,
  disabled = false,
  className = "",
  ariaLabel,
}: ProviderBindingSelectProps) {
  const queryClient = useQueryClient();
  const authData = queryClient.getQueryData<AuthSessionResponse>(["auth", "session"]);
  const canUsePools = hasFeatureAccess(authData?.user, "ai_connections_admin");
  const { data: connectionData } = useQuery({
    queryKey: aiProviderQueryKeys.connections,
    queryFn: fetchAiProviderConnections,
  });
  const { data: poolData } = useQuery({
    queryKey: aiProviderQueryKeys.pools,
    queryFn: fetchAiProviderPools,
    enabled: canUsePools,
  });

  const connections = useMemo(
    () => (connectionData?.connections || []).filter(
      (item) => item.enabled && item.status === "connected" && item.access[mode],
    ),
    [connectionData?.connections, mode],
  );
  const pools = useMemo(
    () => (poolData?.pools || []).filter(
      (pool) => pool.enabled && pool.members.some(
        (member) => member.enabled && member.status === "connected" && member.access?.[mode],
      ),
    ),
    [mode, poolData?.pools],
  );
  const selectedValue = bindingValue(value);
  const hasSelectedOption = !selectedValue
    || connections.some((item) => `connection:${item.id}` === selectedValue)
    || pools.some((item) => `pool:${item.id}` === selectedValue);

  return (
    <select
      value={selectedValue}
      aria-label={ariaLabel ?? localize(lang, "AI-провайдер задачи", "Task AI provider")}
      disabled={disabled}
      onChange={(event) => {
        const [kind, rawId] = event.target.value.split(":");
        const id = Number(rawId);
        if (!kind || !Number.isFinite(id)) {
          onChange(null);
          return;
        }
        if (kind === "connection") {
          const connection = connections.find((item) => item.id === id);
          onChange(connection ? { target_id: connection.target_id, connection_id: id } : null);
          return;
        }
        const pool = pools.find((item) => item.id === id);
        onChange(pool ? { target_id: pool.target_id, pool_id: id } : null);
      }}
      className={`h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
    >
      <option value="">{localize(lang, "По умолчанию для задачи", "Task default")}</option>
      {!hasSelectedOption && selectedValue ? (
        <option value={selectedValue}>{localize(lang, "Недоступная сохранённая привязка", "Unavailable saved binding")}</option>
      ) : null}
      {connections.length ? (
        <optgroup label={localize(lang, "Подключения", "Connections")}>
          {connections.map((connection) => (
            <option key={`connection:${connection.id}`} value={`connection:${connection.id}`}>
              {connection.name} · {connection.target_id === "codex_subscription" ? "Codex CLI" : "Grok CLI"}
            </option>
          ))}
        </optgroup>
      ) : null}
      {pools.length ? (
        <optgroup label={localize(lang, "Пулы", "Pools")}>
          {pools.map((pool) => (
            <option key={`pool:${pool.id}`} value={`pool:${pool.id}`}>
              {pool.name} · {pool.target_id === "codex_subscription" ? "Codex CLI" : "Grok CLI"}
            </option>
          ))}
        </optgroup>
      ) : null}
    </select>
  );
}
