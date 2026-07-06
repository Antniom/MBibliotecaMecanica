import type { APIRoute } from 'astro';
import { json, error, verifyAdminToken, CORS_HEADERS } from '@lib/_auth';

export const prerender = false;

import { env } from 'cloudflare:workers';

export const OPTIONS: APIRoute = () =>
  new Response(null, { status: 204, headers: CORS_HEADERS });

/** GET /api/admin/submissions?status=pending */
export const GET: APIRoute = async ({ request }) => {
  if (!verifyAdminToken(request, env?.ADMIN_TOKEN ?? '')) {
    return error('Não autorizado.', 401);
  }

  const url = new URL(request.url);
  const status = url.searchParams.get('status');

  let stmt;
  if (status) {
    stmt = env.DB.prepare(
      'SELECT * FROM submissions WHERE status = ? ORDER BY created_at DESC LIMIT 200'
    ).bind(status);
  } else {
    stmt = env.DB.prepare(
      'SELECT * FROM submissions ORDER BY created_at DESC LIMIT 200'
    );
  }

  const result = await stmt.all();
  return json({ submissions: result.results });
};
