export class ApiError extends Error {
  method: string;
  path: string;
  status: number;

  constructor(method: string, path: string, status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.method = method;
    this.path = path;
    this.status = status;
  }
}

const API_BASE = import.meta.env.DEV ? "/api" : "";

export type DownloadResult = {
  blob: Blob;
  filename: string;
  exportBatchId: string;
  exportedCount: number;
};

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = init.method ?? "GET";
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.text();
    let message = body || response.statusText;
    try {
      const parsed = JSON.parse(body) as { detail?: unknown; message?: unknown };
      const detail = parsed.detail ?? parsed.message;
      if (typeof detail === "string") message = detail;
      if (detail && typeof detail === "object") message = JSON.stringify(detail);
    } catch {
      // Non-JSON upstream error bodies are shown as returned.
    }
    throw new ApiError(method, path, response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function patchJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteJson<T>(path: string): Promise<T> {
  return request<T>(path, {
    method: "DELETE",
  });
}

export async function postDownload(path: string, body: unknown): Promise<DownloadResult> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    let message = text || response.statusText;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown; message?: unknown };
      const detail = parsed.detail ?? parsed.message;
      if (typeof detail === "string") message = detail;
      if (detail && typeof detail === "object") message = JSON.stringify(detail);
    } catch {
      // Keep the server's plain-text response.
    }
    throw new ApiError("POST", path, response.status, message);
  }
  const disposition = response.headers.get("content-disposition") || "";
  const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
  return {
    blob: await response.blob(),
    filename: filenameMatch?.[1] || "sub2api-credentials.txt",
    exportBatchId: response.headers.get("x-export-batch-id") || "",
    exportedCount: Number(response.headers.get("x-export-count") || 0),
  };
}
