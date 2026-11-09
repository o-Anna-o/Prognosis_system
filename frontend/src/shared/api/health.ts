import { apiRequest } from "./client";

export interface ApiHealth {
  ok: boolean;
}

export function getApiHealth(): Promise<ApiHealth> {
  return apiRequest<ApiHealth>("/api/health");
}
