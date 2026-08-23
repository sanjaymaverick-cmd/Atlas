import { webcrypto } from "node:crypto";

import "fake-indexeddb/auto";

Object.defineProperty(globalThis, "crypto", {
  configurable: true,
  value: webcrypto,
});
