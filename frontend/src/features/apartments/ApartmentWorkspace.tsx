import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getReference, predictApartments } from "../../shared/api/forecasting";
import { useApartmentsActions, useApartmentsState } from "../../contexts/ApartmentsContext";
import { ApartmentCard } from "./ApartmentCard";
import { validateApartment } from "./validation";
import { compareApartments } from "./comparison";
import type { PredictionResult } from "../../shared/api/types";

declare global {
  interface Window { Chart?: new (context: CanvasRenderingContext2D, config: ChartConfig) => { destroy: () => void }; }
}
interface ChartConfig {
  type: "line";
  data: { labels: number[]; datasets: { label: string; data: number[]; borderColor: string; backgroundColor: string; tension: number; pointBackgroundColor: string; pointRadius: number; pointHoverRadius: number; borderWidth: number; fill: boolean }[] };
  options: { responsive: boolean; maintainAspectRatio: boolean; layout: { padding: { top: number } }; interaction: { mode: "nearest"; intersect: boolean }; plugins: { legend: { position: "bottom"; labels: { color: string; font: { size: number } } }; tooltip: { callbacks: { label: (context: { dataset: { label: string }; parsed: { y: number }; dataIndex: number }) => string } }; datalabels: { color: string; anchor: "end"; align: "top"; offset: number; font: { size: number; weight: "bold" }; formatter: (value: number) => string; hover: { color: string; font: { size: number; weight: "bold" } } } }; scales: { x: { title: { display: boolean; text: string }; ticks: { color: string }; grid: { color: string } }; y: { title: { display: boolean; text: string; color: string }; ticks: { color: string }; grid: { color: string } } } };
}

const colors = ["#123A7A", "#0077B6", "#5A189A", "#2563EB", "#7B2CBF", "#005F99", "#4F46E5", "#9D4EDD"];
const money = (rubles: number) => `${Math.round(rubles).toLocaleString("ru-RU")} ₽`;
const moneyMln = (millions: number) => money(millions * 1_000_000);
const priceInMillions = (rubles: number) => `${(rubles / 1_000_000).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} млн руб.`;
function apartmentTitle(order: number, streetValue: string, allStreets: string[]) {
  const street = streetValue.trim();
  if (!street) return "Новая квартира";
  const matchingStreets = allStreets.filter((candidate) => candidate.trim().toLocaleLowerCase("ru-RU") === street.toLocaleLowerCase("ru-RU")).length;
  return matchingStreets > 1 ? `Квартира №${order} на ул. ${street}` : `Квартира на ул. ${street}`;
}
const chartOptions = (label: string, years: number[]): ChartConfig["options"] => ({
  responsive: true,
  maintainAspectRatio: false,
  layout: { padding: { top: 30 } },
  interaction: { mode: "nearest", intersect: false },
  plugins: {
    legend: { position: "bottom", labels: { color: "#0f172a", font: { size: 13 } } },
    tooltip: { callbacks: { label: (item) => ` ${item.dataset.label}: ${item.parsed.y.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} млн руб. (${years[item.dataIndex]} г.)` } },
    datalabels: { color: label, anchor: "end", align: "top", offset: 6, font: { size: 12, weight: "bold" }, formatter: (value) => value.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }), hover: { color: "#0f172a", font: { size: 18, weight: "bold" } } },
  },
  scales: {
    x: { title: { display: true, text: "Год" }, ticks: { color: "#334155" }, grid: { color: "rgba(203, 213, 225, 0.4)" } },
    y: { title: { display: true, text: "млн руб.", color: "#334155" }, ticks: { color: "#334155" }, grid: { color: "rgba(203, 213, 225, 0.4)" } },
  },
});

function ApartmentComparison({ results }: { results: { id: string; order: number; title: string; result: PredictionResult }[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const comparison = useMemo(() => compareApartments(results), [results]);

  useEffect(() => {
    if (!comparison.years.length) return;
    let chart: { destroy: () => void } | undefined;
    const timer = window.setInterval(() => {
      const Chart = window.Chart;
      const canvas = canvasRef.current;
      if (!Chart || !canvas) return;
      window.clearInterval(timer);
      chart = new Chart(canvas.getContext("2d")!, {
        type: "line",
        data: {
          labels: comparison.years,
          datasets: results.map((item) => {
            const points = new Map(item.result.forecast.map((point) => [point.Год, point["Прогноз цены, млн руб."]]));
            if (item.result.base_year <= comparison.years[0]) points.set(item.result.base_year, item.result.base_price / 1_000_000);
            const color = colors[(item.order - 1) % colors.length];
            return { label: item.title, data: comparison.years.map((year) => points.get(year) ?? 0), borderColor: color, backgroundColor: color, pointBackgroundColor: color, tension: 0.25, pointRadius: 5, pointHoverRadius: 7, borderWidth: 2.5, fill: false };
          }),
        },
        options: chartOptions("#1a4fa0", comparison.years),
      });
    }, 100);
    return () => { window.clearInterval(timer); chart?.destroy(); };
  }, [comparison.years, results]);

  if (comparison.rows.length < 2) return <p>Для сравнения рассчитайте не менее двух квартир.</p>;
  const ranked = [...comparison.rows].sort((a, b) => a.place - b.place || a.order - b.order);
  return <div className="card comparison-container">
    <h2 className="card-title">Сравнительный анализ</h2>
    <p>Общий период: {comparison.years[0]}–{comparison.years.at(-1)} гг.</p>
    <h3>Сводная таблица прогнозов по квартирам</h3>
    <div className="table-wrap"><table className="forecast-table comparison-forecast-table">
      <thead><tr><th rowSpan={2}>Год</th>{results.map((item) => <th key={item.id} colSpan={2}>{item.title}</th>)}</tr>
        <tr>{results.flatMap((item) => [<th key={`${item.id}-price`}>Прогноз цены, млн руб.</th>, <th key={`${item.id}-inflation`}>Инфляция, %</th>])}</tr>
      </thead>
      <tbody>{comparison.years.map((year) => <tr key={year}><td>{year}</td>{results.flatMap((item) => {
        const point = item.result.forecast.find((forecast) => forecast.Год === year);
        return [<td key={`${item.id}-${year}-price`}>{point?.["Прогноз цены, млн руб."].toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? "—"}</td>, <td key={`${item.id}-${year}-inflation`}>{point?.["Инфляция, %"].toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) ?? "—"}</td>];
      })}</tr>)}</tbody>
    </table></div>
    <h3>Общий прогноз</h3><div className="chart-wrap comparison-chart"><canvas ref={canvasRef} /></div>
    <h3>Итоговый рейтинг перспективности квартир</h3><div className="table-wrap"><table className="forecast-table"><thead><tr><th>Место</th><th>Улица</th><th>Начальная стоимость</th><th>Конечная стоимость</th><th>Прирост</th><th>Рост, %</th></tr></thead><tbody>
      {ranked.map((row) => <tr key={row.id}><td>{row.place}</td><td>{row.title}</td><td>{moneyMln(row.startPrice)}</td><td>{moneyMln(row.endPrice)}</td><td>{moneyMln(row.change)}</td><td>{row.growth.toFixed(1)}%</td></tr>)}
    </tbody></table></div>
  </div>;
}

function IndividualChart({ result, title, order }: { result: PredictionResult; title: string; order: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let chart: { destroy: () => void } | undefined;
    const timer = window.setInterval(() => {
      const Chart = window.Chart;
      const canvas = canvasRef.current;
      if (!Chart || !canvas) return;
      window.clearInterval(timer);
      chart = new Chart(canvas.getContext("2d")!, {
        type: "line",
        data: { labels: result.forecast.map((point) => point.Год), datasets: [{ label: title, data: result.forecast.map((point) => point["Прогноз цены, млн руб."]), borderColor: colors[(order - 1) % colors.length], backgroundColor: "rgba(37, 99, 235, 0.12)", pointBackgroundColor: "#1a4fa0", tension: 0.25, pointRadius: 5, pointHoverRadius: 7, borderWidth: 2.5, fill: true }] },
        options: chartOptions("#1a4fa0", result.forecast.map((point) => point.Год)),
      });
    }, 100);
    return () => { window.clearInterval(timer); chart?.destroy(); };
  }, [order, result, title]);
  return <div className="chart-wrap"><canvas ref={canvasRef} /></div>;
}

export function ApartmentWorkspace() {
  const { apartments } = useApartmentsState();
  const { addApartment, removeApartment, updateApartmentParameters, setApartmentPrediction, setApartmentError, toggleApartmentCollapsed, setApartmentsCollapsed } = useApartmentsActions();
  const referenceQuery = useQuery({ queryKey: ["reference"], queryFn: ({ signal }) => getReference(signal) });
  const initialized = useRef(false);
  const [activeResultId, setActiveResultId] = useState<string | "comparison">("comparison");

  useEffect(() => { if (!initialized.current) { initialized.current = true; addApartment(); } }, [addApartment]);
  const streets = apartments.map((item) => item.parameters.street);
  const results = apartments.filter((item) => item.prediction && !item.isPredictionStale).map((item) => ({ id: item.id, order: item.order, title: apartmentTitle(item.order, item.prediction!.apartment.street, streets), result: item.prediction! }));
  const addApartmentWithSharedHorizon = () => addApartment({
    region: "", district: "", street: "", wall_material: "", year_build: "", floor: "", area: "",
    n_years: apartments[0]?.parameters.n_years || "5",
  });

  const updateParameters = (id: string, patch: Partial<(typeof apartments)[number]["parameters"]>) => {
    if (id === apartments[0]?.id && patch.n_years !== undefined) {
      updateApartmentParameters(id, patch);
      apartments.filter((apartment) => apartment.id !== id).forEach((apartment) =>
        updateApartmentParameters(apartment.id, { n_years: patch.n_years }),
      );
      return;
    }
    if (patch.n_years !== undefined) {
      const otherChanges = { ...patch };
      delete otherChanges.n_years;
      updateApartmentParameters(id, otherChanges);
      return;
    }
    updateApartmentParameters(id, patch);
  };

  const predict = async (onlyId?: string) => {
    setApartmentsCollapsed(true);
    const selectedApartments = onlyId ? apartments.filter((item) => item.id === onlyId) : apartments;
    const reference = referenceQuery.data;
    if (!selectedApartments.length || !reference) return;
    const validation = selectedApartments.map((apartment) => ({ apartment, errors: validateApartment(apartment.parameters, reference) }));
    if (validation.some(({ errors }) => Object.keys(errors).length > 0)) {
      validation.forEach(({ apartment, errors }) => {
        if (Object.keys(errors).length) setApartmentError(apartment.id, Object.values(errors)[0]!);
      });
      return;
    }
    selectedApartments.forEach((apartment) => setApartmentError(apartment.id, null));
    try {
      const commonHorizon = apartments[0]?.parameters.n_years || "5";
      const input = selectedApartments.map((apartment) => ({
        ...apartment.parameters,
        area: String(apartment.parameters.area).replace(",", "."),
        n_years: commonHorizon,
        client_id: apartment.id,
      }));
      const response = await predictApartments(input);
      selectedApartments.forEach((apartment) => {
        const result = response.results.find((item) => item.client_id === apartment.id)?.prediction;
        if (result) setApartmentPrediction(apartment.id, result);
        else setApartmentError(apartment.id, "Сервер не вернул прогноз для этой квартиры.");
      });
      setActiveResultId(selectedApartments.length > 1 ? "comparison" : selectedApartments[0]!.id);
    } catch (error) {
      selectedApartments.forEach((apartment) => setApartmentError(apartment.id, error instanceof Error ? error.message : "Не удалось выполнить прогноз."));
    }
  };

  if (referenceQuery.isLoading) return <section className="card">Загрузка справочников…</section>;
  if (referenceQuery.error || !referenceQuery.data) return <section className="card error-card" role="alert">Не удалось загрузить справочники: {referenceQuery.error instanceof Error ? referenceQuery.error.message : "ошибка API"}</section>;
  return <>
    <section className="apartment-list" aria-label="Квартиры для прогнозирования">
      {apartments.map((item) => <ApartmentCard key={item.id} id={item.id} order={item.order} apartmentCount={apartments.length} isFirstApartment={item.id === apartments[0]?.id} title={apartmentTitle(item.order, item.parameters.street, streets)} parameters={item.parameters} reference={referenceQuery.data!} collapsed={item.isCollapsed} calculating={item.isCalculating} predictionStale={item.isPredictionStale} error={item.error} onToggleCollapsed={toggleApartmentCollapsed} onRemove={removeApartment} onAdd={addApartmentWithSharedHorizon} onPredict={() => void predict(item.id)} onParameterChange={updateParameters} />)}
    </section>
    {apartments[0]?.isCollapsed && <button type="button" className="btn btn-secondary" onClick={addApartmentWithSharedHorizon}>+ Добавить квартиру</button>}
    {apartments.length > 1 && <div className="form-actions batch-actions"><button type="button" className="btn btn-primary" disabled={apartments.some((item) => item.isCalculating)} onClick={() => void predict()}>{apartments.some((item) => item.isCalculating) ? "Расчёт…" : "Рассчитать прогноз для всех квартир"}</button></div>}
    {results.length > 0 && <>
      <nav className="result-tabs" aria-label="Результаты квартир" role="tablist">
        {results.length >= 2 && <button type="button" role="tab" aria-selected={activeResultId === "comparison"} className={`result-tab ${activeResultId === "comparison" ? "active" : ""}`} onClick={() => setActiveResultId("comparison")}>Сравнительный анализ</button>}
        {results.map((item) => <button key={item.id} type="button" role="tab" aria-selected={activeResultId === item.id} className={`result-tab ${activeResultId === item.id ? "active" : ""}`} onClick={() => setActiveResultId(item.id)}>{item.title}</button>)}
      </nav>
      {activeResultId === "comparison" && results.length >= 2 ? <ApartmentComparison results={results} /> : (() => {
        const item = results.find((entry) => entry.id === activeResultId) || results[0]!;
        return <section className="card result-card"><h2 className="card-title">Прогноз: {item.title}</h2><p>{item.result.apartment.region}, {item.result.apartment.district} · {item.result.apartment.area} м² · {item.result.apartment.floor} этаж · {item.result.apartment.year_build} г. · {item.result.apartment.wall_material}</p><div className="result-summary"><div className="summary-item"><div className="label">Базовая оценка ({item.result.base_year} г.)</div><div className="value">{priceInMillions(item.result.base_price)}</div></div><div className="summary-item"><div className="label">Коэффициент округа</div><div className="value">{item.result.coef_region.toFixed(3)}</div></div><div className="summary-item"><div className="label">Прогноз инфляции</div><div className="value">{item.result.infl_first?.toFixed(1) ?? "—"}% → {item.result.infl_last?.toFixed(1) ?? "—"}%</div></div></div><h3>Прогноз цены по годам</h3><IndividualChart result={item.result} title={item.title} order={item.order} /><div className="table-wrap"><table className="forecast-table"><thead><tr><th>Год</th><th>Прогноз цены, млн руб.</th><th>Инфляция, %</th></tr></thead><tbody>{item.result.forecast.map((point) => <tr key={point.Год}><td>{point.Год}</td><td>{point["Прогноз цены, млн руб."].toLocaleString("ru-RU", { minimumFractionDigits: 2 })}</td><td>{point["Инфляция, %"].toLocaleString("ru-RU", { minimumFractionDigits: 1 })}</td></tr>)}</tbody></table></div></section>;
      })()}
    </>}
  </>;
}
