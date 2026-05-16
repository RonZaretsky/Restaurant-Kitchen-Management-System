const defaults = {
  api: {
    baseUrl: "http://localhost:8000",
    timeoutMs: 5000,
  },
} as const;

const config = {
  api: {
    baseUrl: import.meta.env.VITE_API_BASE_URL ?? defaults.api.baseUrl,
    timeoutMs: Number(import.meta.env.VITE_API_TIMEOUT_MS) || defaults.api.timeoutMs,
  },
} as const;

export default config;
