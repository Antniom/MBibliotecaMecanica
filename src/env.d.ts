/// <reference types="astro/client" />
/// <reference types="@cloudflare/workers-types" />

type Runtime = import('@astrojs/cloudflare').Runtime<Env>;

declare namespace App {
  interface Locals extends Runtime {}
}

interface Env {
  DB: D1Database;
  GITHUB_TOKEN: string;
  GITHUB_REPO: string;
  ADMIN_PASSWORD: string;
  ADMIN_TOKEN: string;
  WORKER_API_TOKEN: string;
}

declare module 'cloudflare:workers' {
  const env: Env;
}
