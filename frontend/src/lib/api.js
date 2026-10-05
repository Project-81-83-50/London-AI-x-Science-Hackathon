// Fetch JSON from the API; a non-2xx response throws an Error carrying FastAPI's `detail` message when present.
export async function apiJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail || `API returned ${response.status}`);
  return body;
}
