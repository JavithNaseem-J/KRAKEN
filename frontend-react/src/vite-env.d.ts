/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GATEWAY_URL?: string;
  readonly VITE_APPROVAL_URL?: string;
  readonly VITE_API_KEY_ALICE?: string;
  readonly VITE_API_KEY_BOB?: string;
  readonly VITE_API_KEY_ADMIN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
