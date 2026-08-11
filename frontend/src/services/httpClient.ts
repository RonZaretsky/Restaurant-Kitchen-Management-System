import config from "../config/config";

/** Shown when the request never reached the backend at all. */
const NETWORK_ERROR_MESSAGE = "Cannot reach the server. Check your connection and try again.";

/** Shown when the backend was reachable but did not answer within the configured budget. */
const TIMEOUT_ERROR_MESSAGE = "The server took too long to respond. Try again.";

/**
 * Raised when a request fails, either because the backend answered with a
 * non-2xx status or because it could not be reached at all.
 *
 * Carries the parsed, human-readable message so callers never have to
 * re-inspect the response body themselves. `status` is 0 when no response ever
 * arrived, which is what lets a caller tell "the server said no" apart from
 * "the server never answered", a distinction the route guard depends on to
 * avoid treating a network blip as a signed-out session.
 */
export class ApiError extends Error {
  status: number;

  /**
   * The underlying failure, when this wraps one.
   *
   * Declared here rather than using the standard `Error.cause`, which needs
   * the ES2022 lib while this project targets ES2020.
   */
  originalError?: unknown;

  /**
   * Builds an ApiError.
   *
   * @param status - The status the backend answered with, or 0 when the
   *   request never reached it.
   * @param message - The human-readable reason, safe to show to a user.
   * @param originalError - The underlying network or parsing failure, kept for
   *   debugging and never shown to a user.
   */
  constructor(status: number, message: string, originalError?: unknown) {
    super(message);
    this.status = status;
    this.originalError = originalError;
  }
}

interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/**
 * Turns a failed response's `detail` field into one readable message.
 *
 * Per the architecture spine's Consistency Conventions, `detail` is either a
 * plain string (app-raised exceptions) or FastAPI's structured validation
 * array (422s). This checks the type rather than assuming it is always a
 * string.
 *
 * @param detail - The parsed response body's `detail` field, of unknown shape.
 * @returns A single human-readable error message.
 */
function extractErrorMessage(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as ValidationError;
    if (typeof first?.msg === "string") {
      return first.msg;
    }
  }
  return "The request was rejected.";
}

/**
 * Builds the request headers, adding a JSON content type only when there is a
 * body to describe.
 *
 * Setting `Content-Type` on a bodyless GET is not CORS-safelisted, so it would
 * force an OPTIONS preflight before every single read. Normalizing through
 * `Headers` also means a caller may pass a `Headers` instance or a tuple array
 * without its entries being silently dropped by an object spread.
 *
 * @param init - The caller's fetch options.
 * @returns The headers to send with the request.
 */
function buildHeaders(init: RequestInit): Headers {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && init.body !== null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

/**
 * Calls the backend API and returns the parsed JSON body.
 *
 * Always sends the session cookie (`credentials: "include"`), the frontend and
 * backend run on different origins even in local dev, so the cookie is never
 * sent without this.
 *
 * Every failure mode leaves as an ApiError, including a dead network and a
 * timeout, so callers can branch on `status` instead of string-matching a raw
 * browser message.
 *
 * @param path - The request path, relative to the configured API base URL.
 * @param init - Standard fetch options. `method`/`body`/extra headers merge on
 *   top of this function's own defaults.
 * @returns The parsed JSON response body, typed as `T`, or undefined for a
 *   response with no body.
 * @throws ApiError if the response status is not in the 2xx range, if the
 *   backend cannot be reached, or if a successful response body cannot be
 *   parsed as JSON.
 */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.api.timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${config.api.baseUrl}${path}`, {
      ...init,
      credentials: "include",
      headers: buildHeaders(init),
      signal: controller.signal,
    });
  } catch (cause) {
    const timedOut = cause instanceof Error && cause.name === "AbortError";
    throw new ApiError(0, timedOut ? TIMEOUT_ERROR_MESSAGE : NETWORK_ERROR_MESSAGE, cause);
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    const body: { detail?: unknown } = await response.json().catch(() => ({}));
    throw new ApiError(response.status, extractErrorMessage(body.detail));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) {
    return undefined as T;
  }

  try {
    return JSON.parse(text) as T;
  } catch (cause) {
    throw new ApiError(response.status, "The server sent a response we could not read.", cause);
  }
}
