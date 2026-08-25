import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies the API rather than calling http://localhost:8000
// directly, so the browser only ever talks to one origin. That matters more
// here than it usually would: a cross-origin call would make the browser send
// the dev server's origin inside the WebAuthn clientDataJSON, and the backend
// compares that against ATLAS_WEBAUTHN_ORIGIN exactly. Same-origin also keeps
// the opaque session token out of any CORS preflight.
//
// The backend must still be started with ATLAS_WEBAUTHN_ORIGIN set to this dev
// server's origin (http://localhost:5173) — see web/README.md. ATLAS_WEBAUTHN_
// RP_ID stays "localhost", because an RP ID is a domain and ignores the port.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: false },
      "/health": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
});
