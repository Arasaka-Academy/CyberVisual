export const API_BASE = import.meta.env.VITE_API_BASE || "";
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly timeout = false,
  ) {
    super(message);
  }
}

export function jsonBody(body: unknown, method = "POST"): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}
export async function getJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  if (init.signal?.aborted) controller.abort();
  init.signal?.addEventListener("abort", abort, { once: true });
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 5000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
    });
    if (!response.ok) {
      let message = `请求失败（HTTP ${response.status}）`;
      try {
        const payload = (await response.json()) as { error?: string };
        if (typeof payload.error === "string") message = payload.error;
      } catch {
        /* Keep the HTTP status when the server returned non-JSON. */
      }
      throw new ApiError(message);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (timedOut) throw new ApiError("请求超时，请检查设备连接后重试。", true);
    throw error;
  } finally {
    window.clearTimeout(timer);
    init.signal?.removeEventListener("abort", abort);
  }
}
