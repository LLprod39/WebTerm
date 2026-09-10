import { beforeEach, afterEach, it, expect, vi } from "vitest";
import { RealtimeConnection } from "@/realtime/socket";
class FakeSocket {
  static OPEN = 1;
  static instances: FakeSocket[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  constructor(public url: URL) {
    FakeSocket.instances.push(this);
  }
}
beforeEach(() => {
  FakeSocket.instances = [];
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", FakeSocket);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
it("does not queue/replay input when disconnected and stops reconnecting after authentication rejection", () => {
  const state = vi.fn();
  const connection = new RealtimeConnection({
    path: "/ws/servers/1/terminal/",
    onMessage: () => {},
    onState: state,
  });
  connection.connect();
  expect(connection.send({ type: "input", data: "rm" })).toBe(false);
  const socket = FakeSocket.instances[0];
  socket.readyState = 1;
  socket.onopen?.();
  expect(socket.send).not.toHaveBeenCalled();
  socket.onclose?.({ code: 4403 });
  vi.runAllTimers();
  expect(FakeSocket.instances).toHaveLength(1);
  expect(state).toHaveBeenLastCalledWith("disconnected");
  connection.close();
});
it("uses bounded backoff and cleanup cancels pending reconnects", () => {
  const connection = new RealtimeConnection({
    path: "/ws/test/",
    onMessage: () => {},
    maxRetries: 2,
  });
  connection.connect();
  FakeSocket.instances[0].onclose?.({ code: 1006 });
  vi.advanceTimersByTime(1500);
  expect(FakeSocket.instances).toHaveLength(2);
  FakeSocket.instances[1].onclose?.({ code: 1006 });
  connection.close();
  vi.runAllTimers();
  expect(FakeSocket.instances).toHaveLength(2);
});
