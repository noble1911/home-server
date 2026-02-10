/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_LIVEKIT_URL: string
  readonly VITE_TUNNEL_DOMAIN: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
