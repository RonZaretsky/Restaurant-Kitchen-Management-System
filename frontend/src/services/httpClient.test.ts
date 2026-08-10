import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiRequest } from "./httpClient";

function mockFetchOnce(response: Partial<Response> & { json: () => Promise<unknown> }) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      ...response,
    } as Response),
  );
}

describe("apiRequest", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends credentials so the session cookie crosses origins", async () => {
    // Arrange
    mockFetchOnce({ json: () => Promise.resolve({ role: "waiter" }) });

    // Act
    await apiRequest("/api/auth/me");

    // Assert
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(init.credentials).toBe("include");
  });

  it("returns the parsed JSON body on success", async () => {
    // Arrange
    mockFetchOnce({ json: () => Promise.resolve({ role: "cook" }) });

    // Act
    const result = await apiRequest<{ role: string }>("/api/auth/me");

    // Assert
    expect(result).toEqual({ role: "cook" });
  });

  it("throws an ApiError carrying the string detail on failure", async () => {
    // Arrange
    mockFetchOnce({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: "Invalid username or password" }),
    });

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
      json: () =>
        Promise.resolve({
          detail: [{ loc: ["body", "username"], msg: "field required", type: "missing" }],
        }),
    });

    // Act / Assert
    await expect(apiRequest("/api/auth/login")).rejects.toMatchObject({
      status: 422,
      message: "field required",
    });
  });
});
