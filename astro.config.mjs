// @ts-check
import { defineConfig } from 'astro/config';
import cloudflare from '@astrojs/cloudflare';
import { fileURLToPath } from 'url';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://astro.build/config
export default defineConfig({
  // Static by default; API routes and server pages opt-in via `export const prerender = false`
  adapter: cloudflare({
    platformProxy: { enabled: true }, // enables D1 in local dev via wrangler
  }),
  vite: {
    resolve: {
      alias: {
        '@lib': path.resolve(__dirname, 'src/lib'),
      },
    },
  },
});
