const BASE_URL = "http://localhost:8000/api";
export const USER_ID = 1;

interface Envelope<T> {
  data: T;
  meta: { request_id: string };
  error: { type: string; detail: unknown } | null;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const body = (await res.json().catch(() => ({}))) as Partial<Envelope<T>> | T;
  if (!res.ok) {
    const detail = (body as Partial<Envelope<T>>).error?.detail;
    throw new Error(detail ? String(detail) : `API ${res.status}: ${res.statusText}`);
  }
  if (body !== null && typeof body === "object" && "data" in body) {
    const env = body as Partial<Envelope<T>>;
    if (env.error) {
      const detail = env.error.detail;
      throw new Error(detail ? String(detail) : `API ${res.status}: ${res.statusText}`);
    }
    return env.data as T;
  }
  return body as T;
}

export { BASE_URL };
