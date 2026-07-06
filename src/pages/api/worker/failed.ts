import type { APIRoute } from 'astro';
import { json, error, verifyWorkerToken, randomId, CORS_HEADERS } from '@lib/_auth';

export const prerender = false;

import { env } from 'cloudflare:workers';

export const OPTIONS: APIRoute = () =>
  new Response(null, { status: 204, headers: CORS_HEADERS });

/** POST /api/worker/failed — mark submission failed and log error */
export const POST: APIRoute = async ({ request }) => {
  if (!verifyWorkerToken(request, env?.WORKER_API_TOKEN ?? '')) {
    return error('Não autorizado.', 401);
  }

  let body: {
    submission_id: string;
    stage: string;
    error_message: string;
    stack_trace?: string;
  };

  try {
    body = await request.json();
  } catch {
    return error('JSON inválido.');
  }

  if (!body.submission_id || !body.stage || !body.error_message) {
    return error('submission_id, stage e error_message são obrigatórios.');
  }

  // Mark failed in D1
  await env.DB.prepare(`
    UPDATE submissions
    SET status = 'failed',
        error_message = ?,
        updated_at = datetime('now')
    WHERE id = ?
  `).bind(body.error_message, body.submission_id).run();

  // Log to error_log
  await env.DB.prepare(`
    INSERT INTO error_log (id, submission_id, stage, error_message, stack_trace)
    VALUES (?, ?, ?, ?, ?)
  `).bind(
    randomId(),
    body.submission_id,
    body.stage,
    body.error_message,
    body.stack_trace ?? null,
  ).run();

  return json({ success: true });
};
