import type { APIRoute } from 'astro';
import { json, error, randomId, CORS_HEADERS } from '@lib/_auth';
import { getOrCreatePendingRelease } from '@lib/_github';

export const prerender = false;

// Allowed file extensions
const ALLOWED_EXTENSIONS = new Set([
  'pdf', 'docx', 'doc', 'pptx', 'ppt', 'odp', 'odt', 'ods', 'xlsx', 'xls',
]);

// 100 MB limit
const MAX_SIZE_BYTES = 100 * 1024 * 1024;

export const OPTIONS: APIRoute = () =>
  new Response(null, { status: 204, headers: CORS_HEADERS });

export const POST: APIRoute = async ({ request, locals }) => {
  const env = locals.runtime?.env as Env;
  if (!env?.GITHUB_TOKEN || !env?.GITHUB_REPO || !env?.DB) {
    return error('Server not configured correctly.', 500);
  }

  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return error('Invalid form data.');
  }

  const file = formData.get('file') as File | null;
  if (!file) return error('Nenhum ficheiro enviado.');

  // Validate extension
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (!ALLOWED_EXTENSIONS.has(ext)) {
    return error(`Tipo de ficheiro não suportado: .${ext}. Suportados: PDF, DOCX, PPTX, ODP, ODT.`);
  }

  // Validate size
  if (file.size > MAX_SIZE_BYTES) {
    return error(`Ficheiro demasiado grande (${(file.size / 1024 / 1024).toFixed(1)} MB). Máximo: 100 MB.`);
  }

  const suggestedDisciplina = (formData.get('disciplina') as string) || null;
  const suggestedTipo = (formData.get('tipo') as string) || null;
  const submitterName = (formData.get('name') as string) || null;
  const notes = (formData.get('notes') as string) || null;

  // ── Upload to GitHub Release ─────────────────────────────────
  let release: any;
  try {
    release = await getOrCreatePendingRelease(env.GITHUB_REPO, env.GITHUB_TOKEN);
  } catch (e: any) {
    return error(`Erro ao preparar armazenamento: ${e.message}`, 500);
  }

  // Parse upload_url (GitHub template: .../assets{?name,label})
  const uploadBase = release.upload_url.replace('{?name,label}', '');
  const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
  const uniqueName = `${Date.now()}_${safeName}`;

  let asset: any;
  try {
    const fileBuffer = await file.arrayBuffer();
    const uploadRes = await fetch(`${uploadBase}?name=${encodeURIComponent(uniqueName)}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'MBibliotecaMecanica/1.0',
        'Content-Type': 'application/octet-stream',
        'Content-Length': file.size.toString(),
      },
      body: fileBuffer,
    });

    if (!uploadRes.ok) {
      const errText = await uploadRes.text();
      throw new Error(`GitHub upload failed (${uploadRes.status}): ${errText}`);
    }

    asset = await uploadRes.json();
  } catch (e: any) {
    return error(`Erro ao fazer upload do ficheiro: ${e.message}`, 500);
  }

  // ── Insert D1 row ────────────────────────────────────────────
  const id = randomId();
  try {
    await env.DB.prepare(`
      INSERT INTO submissions
        (id, file_name, file_size, file_type, github_asset_id, github_asset_url,
         suggested_disciplina, suggested_tipo, submitter_name, notes, status)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    `).bind(
      id,
      file.name,
      file.size,
      ext,
      asset.id,
      asset.browser_download_url,
      suggestedDisciplina,
      suggestedTipo,
      submitterName,
      notes,
    ).run();
  } catch (e: any) {
    // Try to clean up the GitHub asset if DB insert fails
    try {
      await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/releases/assets/${asset.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${env.GITHUB_TOKEN}`, Accept: 'application/vnd.github+json', 'User-Agent': 'MBibliotecaMecanica/1.0' },
      });
    } catch {}
    return error(`Erro ao guardar submissão: ${e.message}`, 500);
  }

  return json({
    id,
    message: 'Submissão recebida com sucesso! Será revisto em breve.',
    fileName: file.name,
  });
};
