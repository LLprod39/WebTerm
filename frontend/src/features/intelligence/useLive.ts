import { useEffect, useRef, useState } from "react";
import { RealtimeConnection, type ConnectionState } from "@/realtime/socket";
import { useSession } from "@/app/session";
import type { Details } from "@/api/intelligence";
export function useLive(
  path: string | null,
  onMessage: (event: Details) => void,
  onOpen?: () => void,
) {
  const { user } = useSession();
  const userId = user?.id;
  const projectId = user?.active_project?.id;
  const callback = useRef(onMessage);
  const opened = useRef(onOpen);
  useEffect(() => {
    callback.current = onMessage;
    opened.current = onOpen;
  }, [onMessage, onOpen]);
  const ref = useRef<RealtimeConnection<Details> | null>(null);
  const [state, setState] = useState<ConnectionState>("disconnected");
  useEffect(() => {
    if (!path || !userId) return;
    const connection = new RealtimeConnection<Details>({
      path,
      onMessage: (event) => callback.current(event),
      onState: setState,
      onOpen: () => opened.current?.(),
    });
    ref.current = connection;
    connection.connect();
    return () => {
      connection.close();
      ref.current = null;
    };
  }, [path, userId, projectId]);
  return {
    state,
    send: (data: unknown) => ref.current?.send(data) ?? false,
    reconnect: () => ref.current?.reconnect(),
  };
}
