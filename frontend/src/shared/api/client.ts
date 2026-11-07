export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type ApiPath =
  | "/api/health"
  | "/api/reference"
  | "/api/predict"
  | "/api/predict/batch";

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: BodyInit | null;
  timeoutMs?: number;
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");
const DEFAULT_TIMEOUT_MS = 30_000;

export async function apiRequest<T>(path: ApiPath, init: ApiRequestOptions = {}): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, ...requestInit } = init;
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");

  const controller = new AbortController();
  const abortFromCaller = () => controller.abort(signal?.reason);
  if (signal?.aborted) {
    abortFromCaller();
  } else {
    signal?.addEventListener("abort", abortFromCaller, { once: true });
  }
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  let body: unknown;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...requestInit,
      signal: controller.signal,
      headers,
    });
    body = await response.json().catch(() => null);
  } finally {
    window.clearTimeout(timeoutId);
    signal?.removeEventListener("abort", abortFromCaller);
  }

  if (!response.ok) {
    const message =
      typeof body === "object" && body !== null && "error" in body && typeof body.error === "string"
        ? body.error
        : `Ошибка API (${response.status})`;
    throw new ApiError(message, response.status);
  }

  return body as T;
}

export { getReference, predictApartment, predictApartments } from "./forecasting";
