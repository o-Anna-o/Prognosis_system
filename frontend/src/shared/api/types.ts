/** Параметры квартиры в формате API прогнозирования. */
export interface ApartmentInput {
  region: string;
  district: string;
  street: string;
  wall_material: string;
  year_build: number | string;
  floor: number | string;
  area: number | string;
  n_years?: number | string | null;
}

/** Сведения о квартире, возвращаемые внутри результата прогноза. */
export interface Apartment {
  region: string;
  district: string;
  street: string;
  wall_material: string;
  year_build: number;
  floor: number;
  area: number;
}

/** Одна строка поля forecast в ответе API. Имена ключей — часть JSON-контракта. */
export interface ForecastPoint {
  Год: number;
  "Прогноз цены, млн руб.": number;
  "Инфляция, %": number;
}

export interface PredictionResult {
  apartment: Apartment;
  base_year: number;
  base_price: number;
  coef_region: number;
  avg_inflation_level: number;
  infl_first: number | null;
  infl_last: number | null;
  forecast: ForecastPoint[];
  /** Точные аналитические значения; возвращаются batch API, одиночный контракт не меняется. */
  base_price_exact?: number;
  forecast_exact?: { year: number; price_mln: number; inflation_pct: number }[];
}

/** Справочник из GET /api/reference. */
export interface ReferenceData {
  regions: string[];
  districts: string[];
  streets: string[];
  region_districts: Record<string, string[]>;
  district_streets: Record<string, string[]>;
  wall_materials: string[];
  region_names: Record<string, string>;
  region_aliases: Record<string, string>;
  district_aliases: Record<string, string>;
  wall_material_aliases: Record<string, string>;
}

export interface BatchApartmentInput extends ApartmentInput {
  client_id: string;
}

export interface BatchPredictionItem {
  client_id: string;
  prediction: PredictionResult;
}

export interface BatchComparisonForecast {
  client_id: string;
  forecast: ForecastPoint[];
  forecast_exact: { year: number; price_mln: number; inflation_pct: number }[];
}

export interface BatchPredictionResult {
  results: BatchPredictionItem[];
  comparison: {
    horizon_years: number;
    base_year: number;
    forecasts: BatchComparisonForecast[];
  };
}
