/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_INCIDENT_STORE_URL?: string;
  readonly VITE_AUDIT_URL?: string;
  readonly VITE_ROUTER_URL?: string;
  readonly VITE_APPROVAL_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
