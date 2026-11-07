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

export function compareApartments(items: ComparableApartment[]): {
  years: number[];
  rows: ComparisonRow[];
} {
  if (items.length < 2) return { years: [], rows: [] };
  const startYear = Math.max(...items.map(({ result }) => result.base_year));
  const endYear = Math.min(...items.map(({ result }) => result.forecast.at(-1)?.Год ?? startYear));
  const years = Array.from({ length: Math.max(0, endYear - startYear) + 1 }, (_, index) => startYear + index);
  const eligible = items.flatMap((item) => {
    const aligned = new Map(item.result.forecast.map((point) => [point.Год, point["Прогноз цены, млн руб."]]));
    const startPrice = item.result.base_year === startYear
      ? item.result.base_price / 1_000_000
      : aligned.get(startYear);
    const endPrice = aligned.get(endYear);
    if (startPrice === undefined || endPrice === undefined || startPrice <= 0) return [];
    return [{ ...item, startPrice, endPrice, change: endPrice - startPrice, growth: (endPrice / startPrice - 1) * 100 }];
  });
  const roundedGrowth = (growth: number) => Number(growth.toFixed(1));
  const ranked = [...eligible].sort((a, b) => roundedGrowth(b.growth) - roundedGrowth(a.growth) || a.order - b.order);
  let place = 0;
  let previousGrowth: number | undefined;
  const placeById = new Map<string, number>();
  ranked.forEach((row, index) => {
    if (previousGrowth === undefined || roundedGrowth(row.growth) !== roundedGrowth(previousGrowth)) place = index + 1;
    placeById.set(row.id, place);
    previousGrowth = row.growth;
  });
  return {
    years,
    rows: eligible.map((row) => ({ ...row, place: placeById.get(row.id) ?? 0 })),
  };
}
