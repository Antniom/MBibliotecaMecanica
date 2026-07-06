// src/lib/_auth.ts
// Shared auth helpers for admin and worker API routes

/**
 * Verify the admin session token from Authorization header.
 * Returns true if valid.
 */
export function verifyAdminToken(request: Request, adminToken: string): boolean {
  const auth = request.headers.get('Authorization') ?? '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
  return token.length > 0 && token === adminToken;
}

/**
 * Verify the worker API token from Authorization header.
 * Returns true if valid.
 */
export function verifyWorkerToken(request: Request, workerToken: string): boolean {
  const auth = request.headers.get('Authorization') ?? '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
  return token.length > 0 && token === workerToken;
}

/** Standard CORS headers for API responses */
export const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PATCH, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

export function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
  });
}

export function error(message: string, status = 400) {
  return json({ error: message }, status);
}

/** Generate a random UUID (Web Crypto API, available in Cloudflare Workers) */
export function randomId(): string {
  return crypto.randomUUID();
}
