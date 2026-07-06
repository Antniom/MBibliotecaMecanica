import type { APIRoute } from 'astro';
import { json, error, verifyWorkerToken, CORS_HEADERS } from '@lib/_auth';
import { deleteAsset } from '@lib/_github';

export const prerender = false;

export const OPTIONS: APIRoute = () =>
  new Response(null, { status: 204, headers: CORS_HEADERS });

/** POST /api/worker/done — mark a submission as successfully processed */
export const POST: APIRoute = async ({ request, locals }) => {
  const env = locals.runtime?.env as Env;
  if (!verifyWorkerToken(request, env?.WORKER_API_TOKEN ?? '')) {
    return error('Não autorizado.', 401);
  }

  let body: { submission_id: string; local_doc_id?: string };
  try {
    body = await request.json();
  } catch {
    return error('JSON inválido.');
  }

  if (!body.submission_id) return error('submission_id em falta.');

  // Get the asset ID before marking done
  const row = await env.DB.prepare(
    'SELECT github_asset_id FROM submissions WHERE id = ?'
  ).bind(body.submission_id).first<{ github_asset_id: number }>();

  // Mark done in D1
  await env.DB.prepare(`
    UPDATE submissions
    SET status = 'done',
        local_doc_id = ?,
        updated_at = datetime('now')
    WHERE id = ?
  `).bind(body.local_doc_id ?? null, body.submission_id).run();

  // Delete the asset from the pending-submissions release (cleanup)
  if (row?.github_asset_id && env.GITHUB_TOKEN && env.GITHUB_REPO) {
    try {
      await deleteAsset(env.GITHUB_REPO, env.GITHUB_TOKEN, row.github_asset_id);
    } catch {
      // Non-fatal — log but don't fail the response
    }
  }

  return json({ success: true });
};
