// Registers the jest-dom matchers (toBeInTheDocument and friends) with vitest's
// expect, loaded by vitest before every test file.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// @testing-library/react's own auto-cleanup detects a global afterEach, which
// vite.config.ts's `globals: false` deliberately does not provide (every test
// file imports describe/it/expect explicitly). Without this, DOM nodes from
// one test in a file leak into the next test in the same file.
afterEach(() => {
  cleanup();
});
