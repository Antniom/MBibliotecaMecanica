import type { APIRoute } from 'astro';
import { json, error, verifyWorkerToken, CORS_HEADERS } from '@lib/_auth';

export const prerender = false;

export const OPTIONS: APIRoute = () =>
  new Response(null, { status: 204, headers: CORS_HEADERS });

/**
 * POST /api/worker/sync
 * Called by worker.py every 30s.
 * - Updates pipeline heartbeat and progress in D1
 * - Returns list of approved submissions for the worker to process
 */
export const POST: APIRoute = async ({ request, locals }) => {
  const env = locals.runtime?.env as Env;
  if (!verifyWorkerToken(request, env?.WORKER_API_TOKEN ?? '')) {
    return error('Não autorizado.', 401);
  }

  let body: {
    status?: string;
    current_doc?: string;
    progress_done?: number;
    progress_total?: number;
    machine_name?: string;
  } = {};

  try {
    body = await request.json();
  } catch {
    // body is optional
  }

  // Update pipeline_status heartbeat
  await env.DB.prepare(`
    UPDATE pipeline_status
    SET status = ?,
        last_heartbeat = datetime('now'),
        current_doc = ?,
        progress_done = ?,
        progress_total = ?,
        machine_name = ?,
        updated_at = datetime('now')
    WHERE id = 1
  `).bind(
    body.status ?? 'idle',
    body.current_doc ?? null,
    body.progress_done ?? 0,
    body.progress_total ?? 0,
    body.machine_name ?? null,
  ).run();

  // Return approved submissions waiting to be processed
  const approved = await env.DB.prepare(`
    SELECT id, file_name, file_size, github_asset_url,
           assigned_disciplina, assigned_tipo, assigned_ano, assigned_semestre
    FROM submissions
    WHERE status IN ('approved', 'downloading', 'processing')
    ORDER BY updated_at ASC
    LIMIT 10
  `).all();

  return json({ approved: approved.results });
};
