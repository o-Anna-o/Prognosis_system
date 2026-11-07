import type { PredictionResult } from "../../shared/api/types";

export interface ComparableApartment {
  id: string;
  order: number;
  title: string;
  result: PredictionResult;
}

export interface ComparisonRow extends ComparableApartment {
  startPrice: number;
  endPrice: number;
  change: number;
  growth: number;
  place: number;
}

export const apartmentColors = [
  "#123A7A", "#0077B6", "#2563EB", "#005F99",
  "#4F46E5", "#4338CA", "#6366F1", "#5A189A",
  "#7B2CBF", "#9D4EDD", "#6B21A8", "#A855F7",
];

export const apartmentMarkers = ["circle", "rect", "triangle", "rectRot", "cross", "star", "line"] as const;

export function apartmentVisual(order: number) {
  const index = Math.max(0, order - 1);
  return {
    color: apartmentColors[index % apartmentColors.length]!,
    marker: apartmentMarkers[index % apartmentMarkers.length]!,
    lineDash: index >= apartmentColors.length ? [6 + (Math.floor(index / apartmentColors.length) % 3) * 3, 4] : [],
  };
}

function exactForecast(result: PredictionResult) {
  return result.forecast_exact
    ? result.forecast_exact.map((point) => [point.year, point.price_mln] as const)
    : result.forecast.map((point) => [point.Год, point["Прогноз цены, млн руб."]] as const);
}

export function growthsEqual(a: number, b: number): boolean {
  return Math.abs(a - b) <= 1e-8 * Math.max(1, Math.abs(a), Math.abs(b));
}

export function compareApartments(items: ComparableApartment[]): {
  years: number[];
  rows: ComparisonRow[];
} {
  if (items.length < 2) return { years: [], rows: [] };
  const startYear = Math.max(...items.map(({ result }) => result.base_year));
  const endYear = Math.min(...items.map(({ result }) => exactForecast(result).at(-1)?.[0] ?? startYear));
  const years = Array.from({ length: Math.max(0, endYear - startYear) + 1 }, (_, index) => startYear + index);
  const eligible = items.flatMap((item) => {
    const aligned = new Map(exactForecast(item.result));
    const exactBase = item.result.base_price_exact ?? item.result.base_price;
    const startPrice = item.result.base_year === startYear
      ? exactBase / 1_000_000
      : aligned.get(startYear);
    const endPrice = aligned.get(endYear);
    if (startPrice === undefined || endPrice === undefined || startPrice <= 0) return [];
    return [{ ...item, startPrice, endPrice, change: endPrice - startPrice, growth: (endPrice - startPrice) / startPrice * 100 }];
  });
  const ranked = [...eligible].sort((a, b) => b.growth - a.growth);
  for (let start = 0; start < ranked.length;) {
    let end = start + 1;
    while (end < ranked.length && growthsEqual(ranked[start]!.growth, ranked[end]!.growth)) end += 1;
    ranked.splice(start, end - start, ...ranked.slice(start, end).sort((a, b) => a.order - b.order));
    start = end;
  }
  let place = 0;
  let previousGrowth: number | undefined;
  const placeById = new Map<string, number>();
  ranked.forEach((row, index) => {
    if (previousGrowth === undefined || !growthsEqual(row.growth, previousGrowth)) place = index + 1;
    placeById.set(row.id, place);
    previousGrowth = row.growth;
  });
  return {
    years,
    rows: eligible.map((row) => ({ ...row, place: placeById.get(row.id) ?? 0 })),
  };
}
