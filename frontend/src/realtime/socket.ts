export type ConnectionState =
  "connecting" | "connected" | "reconnecting" | "disconnected" | "failed";
export interface RealtimeOptions<T> {
  path: string;
  onMessage: (data: T) => void;
  onState?: (state: ConnectionState) => void;
  onOpen?: () => void;
  maxRetries?: number;
}
export class RealtimeConnection<T = Record<string, unknown>> {
  private socket: WebSocket | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private attempts = 0;
  private disposed = false;
  private generation = 0;
  constructor(private options: RealtimeOptions<T>) {}
  connect() {
    this.disposed = false;
    this.open();
  }
  private open() {
    const generation = ++this.generation;
    this.options.onState?.(this.attempts ? "reconnecting" : "connecting");
    const url = new URL(this.options.path, window.location.href);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(url);
    this.socket = socket;
    socket.onopen = () => {
      if (this.disposed || generation !== this.generation) return;
      this.options.onState?.("connected");
      this.options.onOpen?.();
    };
    socket.onmessage = (event) => {
      if (this.disposed || generation !== this.generation) return;
      try {
        const payload = JSON.parse(String(event.data)) as T;
        this.attempts = 0;
        this.options.onMessage(payload);
      } catch {
        this.options.onState?.("failed");
      }
    };
    socket.onerror = () => {
      if (!this.disposed) this.options.onState?.("failed");
    };
    socket.onclose = (event) => {
      if (this.disposed || generation !== this.generation) return;
      this.socket = null;
      if (
        [1000, 1008, 4001, 4003, 4400, 4401, 4403, 4404].includes(event.code)
      ) {
        this.options.onState?.("disconnected");
        return;
      }
      if (this.attempts >= (this.options.maxRetries ?? 5)) {
        this.options.onState?.("failed");
        return;
      }
      this.options.onState?.("reconnecting");
      const delay = Math.min(1500 * 2 ** this.attempts++, 20000);
      this.timer = setTimeout(() => this.open(), delay);
    };
  }
  send(data: unknown) {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(data));
    return true;
  }
  reconnect() {
    this.close();
    this.disposed = false;
    this.attempts = 0;
    this.open();
  }
  close() {
    this.disposed = true;
    ++this.generation;
    clearTimeout(this.timer);
    this.socket?.close(1000);
    this.socket = null;
    this.options.onState?.("disconnected");
  }
}
