import type { APIRoute } from 'astro';
import { json, error, verifyAdminToken, CORS_HEADERS } from '@lib/_auth';

export const prerender = false;

export const OPTIONS: APIRoute = () =>
  new Response(null, { status: 204, headers: CORS_HEADERS });

/** GET /api/admin/status — pipeline status + counts + error log */
export const GET: APIRoute = async ({ request, locals }) => {
  const env = locals.runtime?.env as Env;
  if (!verifyAdminToken(request, env?.ADMIN_TOKEN ?? '')) {
    return error('Não autorizado.', 401);
  }

  const [pipelineRow, countsRow, errors] = await Promise.all([
    env.DB.prepare('SELECT * FROM pipeline_status WHERE id = 1').first(),
    env.DB.prepare(`
      SELECT
        COUNT(*) as total,
        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
        SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
        SUM(CASE WHEN status IN ('downloading','processing') THEN 1 ELSE 0 END) as processing,
        SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
        SUM(CASE WHEN status = 'denied' THEN 1 ELSE 0 END) as denied
      FROM submissions
    `).first(),
    env.DB.prepare(
      'SELECT * FROM error_log ORDER BY created_at DESC LIMIT 50'
    ).all(),
  ]);

  return json({
    pipeline: pipelineRow,
    counts: countsRow,
    errors: errors.results,
  });
};

/** DELETE /api/admin/status — clear error log */
export const DELETE: APIRoute = async ({ request, locals }) => {
  const env = locals.runtime?.env as Env;
  if (!verifyAdminToken(request, env?.ADMIN_TOKEN ?? '')) {
    return error('Não autorizado.', 401);
  }

  await env.DB.prepare('DELETE FROM error_log').run();
  return json({ success: true, message: 'Erros limpos.' });
};
