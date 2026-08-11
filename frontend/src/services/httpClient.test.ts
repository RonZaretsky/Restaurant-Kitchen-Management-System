import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest } from "./httpClient";

function mockFetchOnce({
  ok = true,
  status = 200,
  body = "",
}: {
  ok?: boolean;
  status?: number;
  body?: unknown;
}) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok,
      status,
      text: () => Promise.resolve(text),
      json: () => (text ? Promise.resolve(JSON.parse(text)) : Promise.reject(new SyntaxError())),
    } as unknown as Response),
  );
}

function mockFetchRejectingWith(error: Error) {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(error));
}

function sentInit(): RequestInit {
  const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
  return init;
}

describe("apiRequest", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends credentials so the session cookie crosses origins", async () => {
    // Arrange
    mockFetchOnce({ body: { role: "waiter" } });

    // Act
    await apiRequest("/api/auth/me");

    // Assert
    expect(sentInit().credentials).toBe("include");
  });

  it("returns the parsed JSON body on success", async () => {
    // Arrange
    mockFetchOnce({ body: { role: "cook" } });

    // Act
    const result = await apiRequest<{ role: string }>("/api/auth/me");

    // Assert
    expect(result).toEqual({ role: "cook" });
  });

  it("throws an ApiError carrying the string detail on failure", async () => {
    // Arrange
    mockFetchOnce({ ok: false, status: 401, body: { detail: "Invalid username or password" } });

    // Act / Assert
    await expect(apiRequest("/api/auth/login")).rejects.toMatchObject({
      status: 401,
      message: "Invalid username or password",
    });
    await expect(apiRequest("/api/auth/login")).rejects.toBeInstanceOf(ApiError);
  });

  it("extracts the first message from a FastAPI validation array", async () => {
    // Arrange
    mockFetchOnce({
      ok: false,
      status: 422,
      body: { detail: [{ loc: ["body", "username"], msg: "field required", type: "missing" }] },
    });

    // Act / Assert
    await expect(apiRequest("/api/auth/login")).rejects.toMatchObject({
      status: 422,
      message: "field required",
    });
  });

  it("reports an unreachable backend as an ApiError with status 0, not a raw TypeError", async () => {
    // Arrange
    // Status 0 is what lets the route guard tell "no session" apart from "no
    // server" instead of signing the User out over a network blip.
    mockFetchRejectingWith(new TypeError("Failed to fetch"));

    // Act / Assert
    const rejection = await apiRequest("/api/auth/me").catch((error: unknown) => error);
    expect(rejection).toBeInstanceOf(ApiError);
    expect(rejection).toMatchObject({ status: 0 });
    expect((rejection as ApiError).message).not.toContain("Failed to fetch");
  });

  it("reports a timeout distinctly from a dead network", async () => {
    // Arrange
    const abort = new Error("The operation was aborted.");
    abort.name = "AbortError";
    mockFetchRejectingWith(abort);

    // Act / Assert
    await expect(apiRequest("/api/auth/me")).rejects.toMatchObject({
      status: 0,
      message: expect.stringContaining("too long"),
    });
  });

  it("omits Content-Type on a bodyless request so no CORS preflight is provoked", async () => {
    // Arrange
    mockFetchOnce({ body: { role: "cook" } });

    // Act
    await apiRequest("/api/auth/me");

    // Assert
    expect((sentInit().headers as Headers).has("Content-Type")).toBe(false);
  });

  it("sends Content-Type when there is a body to describe", async () => {
    // Arrange
    mockFetchOnce({ body: { role: "cook" } });

    // Act
    await apiRequest("/api/auth/login", { method: "POST", body: JSON.stringify({ a: 1 }) });

    // Assert
    expect((sentInit().headers as Headers).get("Content-Type")).toBe("application/json");
  });

  it("turns an unparseable success body into an ApiError rather than a SyntaxError", async () => {
    // Arrange
    mockFetchOnce({ body: "<!doctype html><title>proxy</title>" });

    // Act / Assert
    await expect(apiRequest("/api/auth/me")).rejects.toBeInstanceOf(ApiError);
  });
});
