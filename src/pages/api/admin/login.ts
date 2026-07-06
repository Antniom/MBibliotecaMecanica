import type { APIRoute } from 'astro';
import { json, error, CORS_HEADERS } from '@lib/_auth';

export const prerender = false;

export const OPTIONS: APIRoute = () =>
  new Response(null, { status: 204, headers: CORS_HEADERS });

export const POST: APIRoute = async ({ request, locals }) => {
  const env = locals.runtime?.env as Env;
  if (!env?.ADMIN_PASSWORD || !env?.ADMIN_TOKEN) {
    return error('Servidor não configurado.', 500);
  }

  let body: { password?: string };
  try {
    body = await request.json();
  } catch {
    return error('JSON inválido.');
  }

  if (!body.password || body.password !== env.ADMIN_PASSWORD) {
    // Small delay to slow brute-force attempts
    await new Promise((r) => setTimeout(r, 400));
    return error('Palavra-passe incorreta.', 401);
  }

  return json({ token: env.ADMIN_TOKEN, message: 'Login efetuado com sucesso.' });
};
