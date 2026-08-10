import config from "../config/config";

/**
 * Raised when the backend answers with a non-2xx status.
 *
 * Carries the parsed, human-readable message so callers never have to
 * re-inspect the response body themselves.
 */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
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
 * Calls the backend API and returns the parsed JSON body.
 *
 * Always sends the session cookie (`credentials: "include"`), the frontend
 * and backend run on different origins even in local dev, so the cookie is
 * never sent without this.
 *
 * @param path - The request path, relative to the configured API base URL.
 * @param init - Standard fetch options. `method`/`body`/extra headers merge
 *   on top of this function's own defaults.
 * @returns The parsed JSON response body, typed as `T`.
 * @throws ApiError if the response status is not in the 2xx range.
 */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.api.timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${config.api.baseUrl}${path}`, {
      ...init,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...init.headers },
      signal: controller.signal,
    });
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

  return (await response.json()) as T;
}
