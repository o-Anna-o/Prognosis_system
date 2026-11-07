import { apiRequest } from "./client";
import type {
  ApartmentInput,
  BatchApartmentInput,
  BatchPredictionResult,
  PredictionResult,
  ReferenceData,
} from "./types";

function postJson<T>(
  path: "/api/predict" | "/api/predict/batch",
  payload: object,
  signal?: AbortSignal,
): Promise<T> {
  return apiRequest<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
}

export function getReference(signal?: AbortSignal): Promise<ReferenceData> {
  return apiRequest<ReferenceData>("/api/reference", { method: "GET", signal });
}

export function predictApartment(
  apartment: ApartmentInput,
  signal?: AbortSignal,
): Promise<PredictionResult> {
  return postJson<PredictionResult>("/api/predict", apartment, signal);
}

export function predictApartments(
  apartments: BatchApartmentInput[],
  signal?: AbortSignal,
): Promise<BatchPredictionResult> {
  return postJson<BatchPredictionResult>("/api/predict/batch", apartments, signal);
}
