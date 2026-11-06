export const API_BASE = import.meta.env.VITE_API_BASE || "";

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const payload = (await response.json()) as { error?: string };
      if (payload.error) {
        message = payload.error;
      }
    } catch {
      // Keep the HTTP status message when the server returned non-JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
