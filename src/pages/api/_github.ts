// src/pages/api/_github.ts
// Shared GitHub helper used by submit, worker/done, worker/failed

export const PENDING_TAG = 'pending-submissions';
export const PENDING_RELEASE_NAME = 'Submissões Pendentes (Fila de Revisão)';

/**
 * Find or create the draft "pending-submissions" GitHub release.
 * Returns the release object ({ id, upload_url }).
 */
export async function getOrCreatePendingRelease(repo: string, token: string) {
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'MBibliotecaMecanica/1.0',
  };

  // List releases and find the pending one
  const listRes = await fetch(
    `https://api.github.com/repos/${repo}/releases?per_page=100`,
    { headers }
  );

  if (listRes.ok) {
    const releases: any[] = await listRes.json();
    const existing = releases.find((r) => r.tag_name === PENDING_TAG);
    if (existing) return existing;
  }

  // Create it if not found
  const createRes = await fetch(
    `https://api.github.com/repos/${repo}/releases`,
    {
      method: 'POST',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tag_name: PENDING_TAG,
        name: PENDING_RELEASE_NAME,
        draft: true,
        prerelease: false,
        body: 'Esta release contém os ficheiros submetidos pelo público aguardando revisão do administrador.',
      }),
    }
  );

  if (!createRes.ok) {
    const err = await createRes.text();
    throw new Error(`Failed to create GitHub release: ${err}`);
  }

  return createRes.json();
}

/**
 * Delete a GitHub Release asset by its ID.
 */
export async function deleteAsset(repo: string, token: string, assetId: number) {
  await fetch(
    `https://api.github.com/repos/${repo}/releases/assets/${assetId}`,
    {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'MBibliotecaMecanica/1.0',
      },
    }
  );
}
