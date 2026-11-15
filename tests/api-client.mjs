/**
 * API client shared by the browser harnesses.
 *
 * The service requires `X-SKEER-Token` on every write, minted per process by
 * `GET /api/session`, so a harness that posts without it is refused exactly
 * like a foreign page would be. Fetching it here is the honest client
 * behaviour — and it means these scripts fail loudly if the boundary changes.
 */
export function createApiClient(base) {
  let token;
  async function sessionToken() {
    if (token === undefined) {
      token = await fetch(`${base}/api/session`)
        .then((response) => (response.ok ? response.json() : {}))
        .then((payload) => (typeof payload.token === 'string' ? payload.token : ''))
        .catch(() => '');
    }
    return token;
  }

  return async function api(pathname, init = {}) {
    const method = (init.method || 'GET').toUpperCase();
    const headers = { 'Content-Type': 'application/json', ...(init.headers || {}) };
    if (method !== 'GET' && method !== 'HEAD') {
      const value = await sessionToken();
      if (value) headers['X-SKEER-Token'] = value;
    }
    const response = await fetch(`${base}/api${pathname}`, { ...init, method, headers });
    if (!response.ok) {
      throw new Error(`API ${pathname} -> ${response.status}: ${await response.text()}`);
    }
    return response.json();
  };
}
