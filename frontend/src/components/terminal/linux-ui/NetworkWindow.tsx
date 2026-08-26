import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Copy, RefreshCw } from "lucide-react";

import { ListeningSocketRow } from "@/components/terminal/linux-ui/network/ListeningSocketRow";
import { extractSocketPort, isSocketExposed } from "@/components/terminal/linux-ui/network/socketUtils";
import { SummaryCard } from "@/components/terminal/linux-ui/SummaryCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  fetchLinuxUiNetwork,
  type FrontendServer,
  type LinuxUiNetworkInterface,
} from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const EMPTY_NETWORK_INTERFACES: LinuxUiNetworkInterface[] = [];

function NetworkInterfaceRow({
  item,
  selected,
  onClick,
}: {
  item: LinuxUiNetworkInterface;
  selected: boolean;
  onClick: () => void;
}) {
  const { lang } = useI18n();
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
        selected
          ? "border-primary/30 bg-primary/10 shadow-[0_18px_35px_-25px_rgba(0,0,0,0.95)]"
          : "border-border/70 bg-background/88 hover:border-primary/20 hover:bg-secondary/50",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-sm text-foreground">{item.name}</div>
          <div className="mt-1 text-xs text-muted-foreground">{item.kind} {item.mac ? `• ${item.mac}` : ""}</div>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full border px-2 py-0.5 text-xs uppercase tracking-wide",
            item.state === "UP"
              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
              : "border-border/70 bg-background/94 text-muted-foreground",
          )}
        >
          {item.state}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5">
          {localize(lang, `Адресов: ${item.addresses.length}`, `${item.addresses.length} addresses`)}
        </span>
        {item.mtu != null ? (
          <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5">
            mtu {item.mtu}
          </span>
        ) : null}
      </div>
    </button>
  );
}

export function NetworkWindow({
  server,
  active,
  networkEnabled,
}: {
  server: FrontendServer;
  active: boolean;
  networkEnabled: boolean;
}) {
  const { lang } = useI18n();
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());
  const [selectedInterfaceName, setSelectedInterfaceName] = useState<string | null>(null);
  const [selectedSocketKey, setSelectedSocketKey] = useState<string | null>(null);
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null);
  const [protocolFilter, setProtocolFilter] = useState<"all" | "tcp" | "udp">("all");
  const [showUpOnly, setShowUpOnly] = useState(false);
  const [showExposedOnly, setShowExposedOnly] = useState(false);
  const [networkTab, setNetworkTab] = useState<"interfaces" | "sockets" | "routes">("interfaces");

  const networkQuery = useQuery({
    queryKey: ["linux-ui", server.id, "network"],
    queryFn: () => fetchLinuxUiNetwork(server.id),
    enabled: active,
    staleTime: 10_000,
  });

  const networkPayload = networkQuery.data?.network;
  const interfaces = networkPayload?.interfaces ?? EMPTY_NETWORK_INTERFACES;
  const filteredInterfaces = useMemo(() => {
    return interfaces.filter((item) => {
      if (showUpOnly && item.state !== "UP") return false;
      const haystack = [
        item.name,
        item.state,
        item.kind,
        item.mac,
        ...item.flags,
        ...item.addresses.map((address) => `${address.family} ${address.address} ${address.scope}`),
      ]
        .join(" ")
        .toLowerCase();
      return !deferredSearch || haystack.includes(deferredSearch);
    });
  }, [deferredSearch, interfaces, showUpOnly]);

  const filteredListening = useMemo(() => {
    const listening = networkPayload?.listening || [];
    return listening.filter((item) =>
      {
        if (protocolFilter !== "all" && !item.protocol.toLowerCase().includes(protocolFilter)) return false;
        if (showExposedOnly && !isSocketExposed(item.local_address)) return false;
        const haystack = `${item.protocol} ${item.state} ${item.local_address} ${item.peer_address} ${item.process}`.toLowerCase();
        return !deferredSearch || haystack.includes(deferredSearch);
      },
    );
  }, [deferredSearch, networkPayload?.listening, protocolFilter, showExposedOnly]);

  const filteredRoutes = useMemo(() => {
    const routes = networkPayload?.routes || [];
    if (!deferredSearch) return routes;
    return routes.filter((route) => route.toLowerCase().includes(deferredSearch));
  }, [deferredSearch, networkPayload?.routes]);

  useEffect(() => {
    if (!interfaces.length) {
      if (selectedInterfaceName != null) setSelectedInterfaceName(null);
      return;
    }
    if (!filteredInterfaces.some((item) => item.name === selectedInterfaceName)) {
      setSelectedInterfaceName((filteredInterfaces[0] || interfaces[0]).name);
    }
  }, [filteredInterfaces, interfaces, selectedInterfaceName]);

  const selectedInterface = useMemo(() => {
    return interfaces.find((item) => item.name === selectedInterfaceName) || filteredInterfaces[0] || interfaces[0] || null;
  }, [filteredInterfaces, interfaces, selectedInterfaceName]);

  useEffect(() => {
    if (!filteredListening.length) {
      if (selectedSocketKey != null) setSelectedSocketKey(null);
      return;
    }
    const socketKeys = filteredListening.map((item) => `${item.protocol}:${item.local_address}:${item.process}`);
    if (!selectedSocketKey || !socketKeys.includes(selectedSocketKey)) {
      setSelectedSocketKey(socketKeys[0]);
    }
  }, [filteredListening, selectedSocketKey]);

  const selectedSocket = useMemo(() => {
    return filteredListening.find((item) => `${item.protocol}:${item.local_address}:${item.process}` === selectedSocketKey) || filteredListening[0] || null;
  }, [filteredListening, selectedSocketKey]);

  useEffect(() => {
    if (!filteredRoutes.length) {
      if (selectedRoute != null) setSelectedRoute(null);
      return;
    }
    if (!selectedRoute || !filteredRoutes.includes(selectedRoute)) {
      setSelectedRoute(filteredRoutes[0]);
    }
  }, [filteredRoutes, selectedRoute]);

  const selectedSocketPort = selectedSocket ? extractSocketPort(selectedSocket.local_address) : "";
  const exposedCount = filteredListening.filter((item) => isSocketExposed(item.local_address)).length;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="border-b border-border/60 px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="text-sm font-medium text-foreground">{localize(lang, "Сеть", "Network")}</div>
            <div className="mt-1 text-xs text-muted-foreground">{localize(lang, "Интерфейсы, маршруты и открытые порты.", "Interfaces, routes, and listening ports.")}</div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={localize(lang, "Найти интерфейс, порт или маршрут...", "Filter interfaces, ports, or routes...")}
              className="h-9 min-w-[16rem] bg-background/95 text-sm"
            />
            <Button type="button" size="sm" variant="outline" className="h-9 gap-1.5 text-xs" onClick={() => void networkQuery.refetch()}>
              <RefreshCw className={cn("h-3.5 w-3.5", networkQuery.isFetching && "animate-spin")} />
              {localize(lang, "Обновить", "Refresh")}
            </Button>
          </div>
        </div>
        {!networkEnabled ? (
          <div className="mt-3 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            {localize(lang, "Данные ограничены возможностями ip, ss и резервных команд.", "Data is limited to what ip, ss, and fallback commands can provide.")}
          </div>
        ) : null}
        <div className="mt-4 grid gap-2 md:grid-cols-4">
          <SummaryCard label={localize(lang, "Интерфейсы", "Interfaces")} value={networkPayload?.summary.interfaces || 0} hint={localize(lang, "Обнаруженные подключения", "Detected links")} />
          <SummaryCard label={localize(lang, "Адреса", "Addresses")} value={networkPayload?.summary.addresses || 0} hint={localize(lang, "IPv4 и IPv6", "IPv4 and IPv6")} />
          <SummaryCard label={localize(lang, "Маршруты", "Routes")} value={networkPayload?.summary.routes || 0} hint={localize(lang, "Записи таблицы маршрутизации", "Route entries")} />
          <SummaryCard label={localize(lang, "Слушают", "Listening")} value={networkPayload?.summary.listening || 0} hint={localize(lang, "Открытые сокеты", "Listening sockets")} alert={(networkPayload?.summary.listening || 0) > 0} />
        </div>
        <div className="mt-4 flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" variant={showUpOnly ? "default" : "outline"} className="h-9 text-xs" onClick={() => setShowUpOnly((current) => !current)}>
              {localize(lang, "Только активные", "Up only")}
            </Button>
            <Button type="button" size="sm" variant={showExposedOnly ? "default" : "outline"} className="h-9 text-xs" onClick={() => setShowExposedOnly((current) => !current)}>
              {localize(lang, "Только внешние", "Exposed only")}
            </Button>
            {([
              { value: "all", label: localize(lang, "Все протоколы", "All protocols") },
              { value: "tcp", label: "TCP" },
              { value: "udp", label: "UDP" },
            ] as const).map((item) => (
              <Button
                key={item.value}
                type="button"
                size="sm"
                variant={protocolFilter === item.value ? "default" : "outline"}
                className="h-9 text-xs"
                onClick={() => setProtocolFilter(item.value)}
              >
                {item.label}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="rounded-full border border-border/70 bg-background/94 px-2 py-1">
              ip {networkPayload?.tools.ip ? localize(lang, "доступен", "ready") : localize(lang, "нет", "missing")}
            </span>
            <span className="rounded-full border border-border/70 bg-background/94 px-2 py-1">
              ss {networkPayload?.tools.ss ? localize(lang, "доступен", "ready") : localize(lang, "нет", "missing")}
            </span>
            <span className="rounded-full border border-destructive/20 bg-destructive/10 px-2 py-1 text-destructive">
              {localize(lang, `Внешних: ${exposedCount}`, `Exposed: ${exposedCount}`)}
            </span>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-4">
        <div className="grid h-full min-h-0 gap-4 xl:grid-cols-[18rem_minmax(0,1fr)]">
          <section className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
            <div className="border-b border-border/60 px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{localize(lang, "Интерфейсы", "Interfaces")}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {localize(lang, `Показано ${filteredInterfaces.length} из ${interfaces.length}`, `${filteredInterfaces.length} of ${interfaces.length} visible`)}
              </div>
            </div>
            <ScrollArea className="h-full max-h-full">
              <div className="space-y-2 p-3">
                {networkQuery.error instanceof Error ? (
                  <div className="rounded-2xl border border-destructive/35 bg-destructive/10 px-3 py-3 text-sm text-destructive">
                    {networkQuery.error.message}
                  </div>
                ) : null}
                {networkQuery.isLoading ? (
                  <div className="rounded-2xl border border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    {localize(lang, "Загружаем данные сети...", "Loading network data...")}
                  </div>
                ) : null}
                {!networkQuery.isLoading && filteredInterfaces.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                    {localize(lang, "Ничего не найдено.", "No interfaces match the current filter.")}
                  </div>
                ) : null}
                {filteredInterfaces.map((item) => (
                  <NetworkInterfaceRow
                    key={item.name}
                    item={item}
                    selected={selectedInterfaceName === item.name}
                    onClick={() => setSelectedInterfaceName(item.name)}
                  />
                ))}
              </div>
            </ScrollArea>
          </section>

          <section className="grid min-h-0 gap-4 lg:grid-rows-[auto_auto_minmax(0,1fr)_14rem]">
            <div className="rounded-3xl border border-border/70 bg-background/88 px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                {([
                  { value: "interfaces", label: localize(lang, `Интерфейсы (${filteredInterfaces.length})`, `Interfaces (${filteredInterfaces.length})`) },
                  { value: "sockets", label: localize(lang, `Сокеты (${filteredListening.length})`, `Sockets (${filteredListening.length})`) },
                  { value: "routes", label: localize(lang, `Маршруты (${filteredRoutes.length})`, `Routes (${filteredRoutes.length})`) },
                ] as const).map((item) => (
                  <Button
                    key={item.value}
                    type="button"
                    size="sm"
                    variant={networkTab === item.value ? "default" : "outline"}
                    className="h-8 text-xs"
                    onClick={() => setNetworkTab(item.value)}
                  >
                    {item.label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="rounded-3xl border border-border/70 bg-background/88 p-4">
              {networkTab === "interfaces" && selectedInterface ? (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-mono text-sm text-foreground">{selectedInterface.name}</h3>
                      <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
                        {selectedInterface.state}
                      </span>
                      {selectedInterface.mtu != null ? (
                        <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
                          mtu {selectedInterface.mtu}
                        </span>
                      ) : null}
                    </div>
                    <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={() => void navigator.clipboard.writeText(selectedInterface.name)}>
                      <Copy className="mr-1.5 h-3.5 w-3.5" />
                      {localize(lang, "Копировать имя", "Copy interface")}
                    </Button>
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    {selectedInterface.kind} {selectedInterface.mac ? `• ${selectedInterface.mac}` : ""}
                  </div>
                  <div className="mt-4 grid gap-2 lg:grid-cols-2">
                    <div className="rounded-2xl border border-border/70 bg-card/88 p-3">
                      <div className="text-xs uppercase tracking-wide text-muted-foreground">{localize(lang, "Адреса", "Addresses")}</div>
                      <div className="mt-2 space-y-2">
                        {selectedInterface.addresses.length > 0 ? selectedInterface.addresses.map((address) => (
                          <div key={`${address.family}-${address.address}`} className="rounded-xl border border-border/70 bg-background/94 px-3 py-2">
                            <div className="font-mono text-xs text-foreground">{address.address}</div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {address.family}{address.scope ? ` • ${address.scope}` : ""}
                            </div>
                          </div>
                        )) : (
                          <div className="text-xs text-muted-foreground">{localize(lang, "Адресов нет.", "No addresses detected.")}</div>
                        )}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-border/70 bg-card/88 p-3">
                      <div className="text-xs uppercase tracking-wide text-muted-foreground">{localize(lang, "Флаги", "Flags")}</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {selectedInterface.flags.length > 0 ? selectedInterface.flags.map((flag) => (
                          <span key={flag} className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
                            {flag}
                          </span>
                        )) : (
                          <div className="text-xs text-muted-foreground">{localize(lang, "Флагов нет.", "No flags reported.")}</div>
                        )}
                      </div>
                    </div>
                  </div>
                </>
              ) : null}
              {networkTab === "sockets" && selectedSocket ? (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-mono text-sm text-foreground">{selectedSocket.local_address || "n/a"}</h3>
                      <span className="rounded-full border border-border/70 bg-background/94 px-2 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
                        {selectedSocket.protocol}
                      </span>
                      {isSocketExposed(selectedSocket.local_address) ? (
                        <span className="rounded-full border border-destructive/20 bg-destructive/10 px-2 py-0.5 text-xs uppercase tracking-wide text-destructive">
                          {localize(lang, "внешний", "exposed")}
                        </span>
                      ) : null}
                    </div>
                    <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={() => void navigator.clipboard.writeText(selectedSocket.local_address)}>
                      <Copy className="mr-1.5 h-3.5 w-3.5" />
                      {localize(lang, "Копировать сокет", "Copy socket")}
                    </Button>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-3">
                    <SummaryCard label={localize(lang, "Порт", "Port")} value={selectedSocketPort || "N/A"} hint={localize(lang, "Из адреса привязки", "From bind address")} />
                    <SummaryCard label={localize(lang, "Состояние", "State")} value={selectedSocket.state || "unknown"} hint={localize(lang, "Состояние слушателя", "Listener state")} />
                    <SummaryCard label={localize(lang, "Доступ", "Exposure")} value={isSocketExposed(selectedSocket.local_address) ? localize(lang, "Внешний", "Public") : localize(lang, "Локальный", "Local")} hint={localize(lang, "Область привязки", "Bind scope")} alert={isSocketExposed(selectedSocket.local_address)} />
                  </div>
                  <div className="rounded-2xl border border-border/70 bg-card/88 p-3">
                    <div className="text-xs uppercase tracking-wide text-muted-foreground">{localize(lang, "Процесс", "Process")}</div>
                    <div className="mt-2 font-mono text-xs text-foreground">{selectedSocket.process || localize(lang, "Процесс не определён", "Process metadata unavailable")}</div>
                    <div className="mt-2 text-xs text-muted-foreground">{selectedSocket.peer_address || localize(lang, "Нет данных об удалённой стороне", "No peer metadata")}</div>
                  </div>
                </div>
              ) : null}
              {networkTab === "routes" ? (
                selectedRoute ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="text-sm font-medium text-foreground">{localize(lang, "Выбранный маршрут", "Selected route")}</h3>
                      <Button type="button" size="sm" variant="outline" className="h-8 text-xs" onClick={() => void navigator.clipboard.writeText(selectedRoute)}>
                        <Copy className="mr-1.5 h-3.5 w-3.5" />
                        {localize(lang, "Копировать маршрут", "Copy route")}
                      </Button>
                    </div>
                    <pre className="whitespace-pre-wrap break-words rounded-2xl border border-border/70 bg-card/88 px-3 py-3 font-mono text-xs leading-5 text-foreground">
                      {selectedRoute}
                    </pre>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">{localize(lang, "Выберите маршрут.", "Select a route.")}</div>
                )
              ) : null}
            </div>

            <div className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
              <div className="border-b border-border/60 px-4 py-3">
                <div className="text-sm font-medium text-foreground">{localize(lang, "Слушающие сокеты", "Listening sockets")}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {localize(lang, `Показано: ${filteredListening.length}`, `${filteredListening.length} sockets visible`)}
                </div>
              </div>
              <ScrollArea className="h-full max-h-full">
                <div className="space-y-2 p-3">
                  {filteredListening.length > 0 ? filteredListening.map((item, index) => {
                    const socketKey = `${item.protocol}:${item.local_address}:${item.process}`;
                    return (
                      <ListeningSocketRow
                        key={`${socketKey}-${index}`}
                        item={item}
                        selected={selectedSocketKey === socketKey}
                        onClick={() => {
                          setSelectedSocketKey(socketKey);
                          setNetworkTab("sockets");
                        }}
                      />
                    );
                  }) : (
                    <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                      {localize(lang, "Ничего не найдено.", "No listening sockets match the current filter.")}
                    </div>
                  )}
                </div>
              </ScrollArea>
            </div>

            <div className="min-h-0 overflow-hidden rounded-3xl border border-border/70 bg-background/88">
              <div className="border-b border-border/60 px-4 py-3">
                <div className="text-sm font-medium text-foreground">{localize(lang, "Маршруты", "Routes")}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {localize(lang, `Показано: ${filteredRoutes.length}`, `${filteredRoutes.length} routes visible`)}
                </div>
              </div>
              <ScrollArea className="h-full">
                <div className="space-y-2 p-3">
                  {filteredRoutes.length > 0 ? filteredRoutes.map((route) => (
                    <button
                      key={route}
                      type="button"
                      onClick={() => {
                        setSelectedRoute(route);
                        setNetworkTab("routes");
                      }}
                      className={cn(
                        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
                        selectedRoute === route
                          ? "border-primary/30 bg-primary/10"
                          : "border-border/70 bg-background/90 hover:border-primary/20 hover:bg-secondary/50",
                      )}
                    >
                      <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-5 text-foreground">{route}</pre>
                    </button>
                  )) : (
                    <div className="rounded-2xl border border-dashed border-border/70 bg-background/92 px-3 py-6 text-center text-sm text-muted-foreground">
                      {localize(lang, "Ничего не найдено.", "No routes match the current filter.")}
                    </div>
                  )}
                </div>
              </ScrollArea>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
