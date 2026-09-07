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
