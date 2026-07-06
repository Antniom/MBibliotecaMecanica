import type { APIRoute } from 'astro';
import { json, error, verifyAdminToken, CORS_HEADERS } from '@lib/_auth';

export const prerender = false;

export const OPTIONS: APIRoute = () =>
  new Response(null, { status: 204, headers: CORS_HEADERS });

/** PATCH /api/admin/submissions/[id] — approve or deny */
export const PATCH: APIRoute = async ({ request, locals, params }) => {
  const env = locals.runtime?.env as Env;
  if (!verifyAdminToken(request, env?.ADMIN_TOKEN ?? '')) {
    return error('Não autorizado.', 401);
  }

  const id = params.id;
  if (!id) return error('ID em falta.');

  let body: {
    action: 'approve' | 'deny';
    disciplina?: string;
    tipo?: string;
    ano?: number;
    semestre?: number;
  };

  try {
    body = await request.json();
  } catch {
    return error('JSON inválido.');
  }

  if (body.action === 'approve') {
    if (!body.disciplina || !body.tipo || !body.ano || !body.semestre) {
      return error('Disciplina, tipo, ano e semestre são obrigatórios para aprovar.');
    }

    await env.DB.prepare(`
      UPDATE submissions
      SET status = 'approved',
          assigned_disciplina = ?,
          assigned_tipo = ?,
          assigned_ano = ?,
          assigned_semestre = ?,
          updated_at = datetime('now')
      WHERE id = ?
    `).bind(body.disciplina, body.tipo, body.ano, body.semestre, id).run();

    return json({ success: true, message: 'Submissão aprovada.' });

  } else if (body.action === 'deny') {
    await env.DB.prepare(`
      UPDATE submissions
      SET status = 'denied',
          updated_at = datetime('now')
      WHERE id = ?
    `).bind(id).run();

    return json({ success: true, message: 'Submissão rejeitada.' });

  } else {
    return error('Ação inválida. Use "approve" ou "deny".');
  }
};

/** GET /api/admin/submissions/[id] — get single submission */
export const GET: APIRoute = async ({ request, locals, params }) => {
  const env = locals.runtime?.env as Env;
  if (!verifyAdminToken(request, env?.ADMIN_TOKEN ?? '')) {
    return error('Não autorizado.', 401);
  }

  const id = params.id;
  const result = await env.DB.prepare(
    'SELECT * FROM submissions WHERE id = ?'
  ).bind(id).first();

  if (!result) return error('Submissão não encontrada.', 404);
  return json(result);
};
