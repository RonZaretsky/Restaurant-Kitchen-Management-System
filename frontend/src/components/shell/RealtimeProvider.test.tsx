import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useConnectionStatus } from "./ConnectionStatusContext";
import { RealtimeProvider, useRealtime } from "./RealtimeProvider";

/**
 * A minimal stand-in for the browser's WebSocket.
 *
 * jsdom's real WebSocket (present since jsdom 30) attempts an actual, slow,
 * eventually-failing network connection, which is exactly the
 * non-deterministic behavior these tests need to avoid. This fake never
 * sends anything (RealtimeProvider never calls .send either, matching AD-2's
 * "Clients never treat the WebSocket as a write channel"), it only exposes
 * the four handlers RealtimeProvider assigns, a close() the test can trigger
 * to simulate a drop (optionally with a close code), and a readyState so a
 * test can tell a superseded socket apart from the live one.
 */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  url: string;
  readyState = 1; // OPEN
  onopen: (() => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close(code = 1006) {
    this.readyState = 3; // CLOSED
    this.onclose?.({ code });
  }
}

function Probe() {
  const status = useConnectionStatus();
  const { subscribe } = useRealtime();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <button
        onClick={() =>
          subscribe("test.event", (payload) => {
            document.title = JSON.stringify(payload);
          })
        }
      >
        subscribe
      </button>
      <button
        onClick={() =>
          subscribe("test.event", () => {
            throw new Error("a subscriber that misbehaves");
          })
        }
      >
        subscribe-throwing
      </button>
    </div>
  );
}

function renderProbe() {
  return render(
    <RealtimeProvider>
      <Probe />
    </RealtimeProvider>,
  );
}

describe("RealtimeProvider", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("starts connected, since nothing has dropped yet at first mount", () => {
    // Arrange / Act
    renderProbe();

    // Assert
    expect(screen.getByTestId("status")).toHaveTextContent("connected");
  });

  it("flips to reconnecting when the socket closes", () => {
    // Arrange
    renderProbe();
    act(() => FakeWebSocket.instances[0].onopen?.());
    expect(screen.getByTestId("status")).toHaveTextContent("connected");

    // Act
    act(() => FakeWebSocket.instances[0].close());

    // Assert
    expect(screen.getByTestId("status")).toHaveTextContent("reconnecting");
  });

  it("retries automatically after a drop, with growing backoff", () => {
    // Arrange
    renderProbe();
    act(() => FakeWebSocket.instances[0].onopen?.());
    act(() => FakeWebSocket.instances[0].close());
    expect(FakeWebSocket.instances).toHaveLength(1);

    // Act: first retry fires at the initial 1s delay
    act(() => vi.advanceTimersByTime(1000));

    // Assert
    expect(FakeWebSocket.instances).toHaveLength(2);

    // Act: that attempt also fails; the second retry must wait longer (backoff grows)
    act(() => FakeWebSocket.instances[1].close());
    act(() => vi.advanceTimersByTime(1000));
    expect(FakeWebSocket.instances).toHaveLength(2); // not yet, delay doubled to 2s

    act(() => vi.advanceTimersByTime(1000));
    expect(FakeWebSocket.instances).toHaveLength(3); // now it has
  });

  it("resets the backoff delay after a successful reconnect", () => {
    // Arrange
    renderProbe();
    act(() => FakeWebSocket.instances[0].onopen?.());
    act(() => FakeWebSocket.instances[0].close());
    act(() => vi.advanceTimersByTime(1000));
    expect(FakeWebSocket.instances).toHaveLength(2);

    // Act: this reconnect succeeds, so the next drop should retry at 1s again, not 4s
    act(() => FakeWebSocket.instances[1].onopen?.());
    act(() => FakeWebSocket.instances[1].close());
    act(() => vi.advanceTimersByTime(1000));

    // Assert
    expect(FakeWebSocket.instances).toHaveLength(3);
  });

  it("caps the backoff delay at MAX_RETRY_DELAY_MS instead of doubling forever", () => {
    // Arrange: drive the delay past its cap: 1s, 2s, 4s, 8s, 16s, then 30s (capped, not 32s).
    renderProbe();
    act(() => FakeWebSocket.instances[0].close());
    for (let i = 0; i < 5; i++) {
      const delayMs = 1000 * 2 ** i;
      act(() => vi.advanceTimersByTime(delayMs));
      act(() => FakeWebSocket.instances[FakeWebSocket.instances.length - 1].close());
    }
    expect(FakeWebSocket.instances).toHaveLength(6);

    // Act: the next delay would be 32s uncapped; at 30s (the cap) it must already have retried.
    act(() => vi.advanceTimersByTime(30_000));

    // Assert
    expect(FakeWebSocket.instances).toHaveLength(7);
  });

  it("does not retry after a 1008 policy-violation close", () => {
    // Arrange
    renderProbe();
    act(() => FakeWebSocket.instances[0].onopen?.());

    // Act: the backend closes with 1008 (expired session, disallowed Origin, ...).
    act(() => FakeWebSocket.instances[0].close(1008));

    // Assert: status reflects the drop, but no reconnect is scheduled -- retrying
    // against a session the server just rejected would be pointless.
    expect(screen.getByTestId("status")).toHaveTextContent("reconnecting");
    act(() => vi.advanceTimersByTime(60_000));
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("does not retry after a 4409 connection-replaced close, and reports it distinctly", () => {
    // Arrange
    renderProbe();
    act(() => FakeWebSocket.instances[0].onopen?.());

    // Act: the backend closes with 4409 because another tab's connection took this one's place
    // (ConnectionRegistry.register in backend/clients/websocket.py).
    act(() => FakeWebSocket.instances[0].close(4409));

    // Assert: a distinct status from a plain drop, and no reconnect is scheduled -- retrying
    // would just steal the connection back and repeat the takeover forever.
    expect(screen.getByTestId("status")).toHaveTextContent("replaced");
    act(() => vi.advanceTimersByTime(60_000));
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("closes the socket when onerror fires", () => {
    // Arrange
    renderProbe();
    const socket = FakeWebSocket.instances[0];
    const closeSpy = vi.spyOn(socket, "close");

    // Act
    act(() => socket.onerror?.());

    // Assert
    expect(closeSpy).toHaveBeenCalled();
  });

  it("ignores a close from a socket that has already been superseded", () => {
    // Arrange: drop and let the automatic retry create a second, current socket.
    renderProbe();
    act(() => FakeWebSocket.instances[0].close());
    act(() => vi.advanceTimersByTime(1000));
    expect(FakeWebSocket.instances).toHaveLength(2);
    act(() => FakeWebSocket.instances[1].onopen?.());
    expect(screen.getByTestId("status")).toHaveTextContent("connected");

    // Act: the stale first socket fires its close late, after being superseded.
    act(() => FakeWebSocket.instances[0].close());

    // Assert: the current connection's status is untouched, and no extra retry fires.
    expect(screen.getByTestId("status")).toHaveTextContent("connected");
    act(() => vi.advanceTimersByTime(60_000));
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("does not reconnect after unmount, even if a pending retry timer was already scheduled", () => {
    // Arrange: a drop schedules a retry timer.
    const { unmount } = renderProbe();
    act(() => FakeWebSocket.instances[0].close());
    expect(FakeWebSocket.instances).toHaveLength(1);

    // Act
    unmount();
    act(() => vi.advanceTimersByTime(60_000));

    // Assert: the scheduled retry never created a second socket.
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("delivers a subscribed event's payload when the socket receives it", () => {
    // Arrange
    renderProbe();
    act(() => FakeWebSocket.instances[0].onopen?.());
    screen.getByRole("button", { name: "subscribe" }).click();

    // Act
    act(() =>
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({ event: "test.event", payload: { ok: true } }),
      }),
    );

    // Assert
    expect(document.title).toBe('{"ok":true}');
  });

  it("ignores a well-formed frame whose payload is not the expected shape", () => {
    // Arrange
    renderProbe();
    act(() => FakeWebSocket.instances[0].onopen?.());
    screen.getByRole("button", { name: "subscribe" }).click();
    document.title = "untouched";

    // Act: valid JSON, but not an {event, payload} object.
    act(() => FakeWebSocket.instances[0].onmessage?.({ data: "null" }));
    act(() => FakeWebSocket.instances[0].onmessage?.({ data: "42" }));

    // Assert: no subscriber was invoked, and nothing threw.
    expect(document.title).toBe("untouched");
  });

  it("keeps delivering to other subscribers when one handler throws", () => {
    // Arrange: a throwing subscriber and a well-behaved one, both on the same event.
    renderProbe();
    act(() => FakeWebSocket.instances[0].onopen?.());
    screen.getByRole("button", { name: "subscribe-throwing" }).click();
    screen.getByRole("button", { name: "subscribe" }).click();

    // Act
    act(() =>
      FakeWebSocket.instances[0].onmessage?.({
        data: JSON.stringify({ event: "test.event", payload: { ok: true } }),
      }),
    );

    // Assert: the well-behaved handler still ran, and nothing escaped to the socket.
    expect(document.title).toBe('{"ok":true}');
  });

  it("closes the socket on unmount", () => {
    // Arrange
    const { unmount } = renderProbe();
    const socket = FakeWebSocket.instances[0];
    const closeSpy = vi.spyOn(socket, "close");

    // Act
    unmount();

    // Assert
    expect(closeSpy).toHaveBeenCalled();
  });
});
