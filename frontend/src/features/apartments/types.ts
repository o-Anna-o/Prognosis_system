import type { ApartmentInput, PredictionResult } from "../../shared/api/types";

export interface ApartmentState {
  /** UUID используется для связи квартиры и её прогноза; адрес может повторяться. */
  id: string;
  /** Порядковый номер добавления. При удалении других квартир не меняется. */
  order: number;
  /** Перемонтирует поля формы при общем сбросе, очищая локальные ошибки ввода. */
  formRevision: number;
  parameters: ApartmentInput;
  prediction: PredictionResult | null;
  isPredictionStale: boolean;
  isCollapsed: boolean;
  isCalculating: boolean;
  error: string | null;
}

export interface ApartmentsState {
  apartments: ApartmentState[];
  activeApartmentId: string | null;
  nextOrder: number;
}

export type ApartmentParameterPatch = Partial<ApartmentInput>;
