import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getReference, predictApartment, predictApartments } from "../../shared/api/forecasting";
import { useApartmentsActions, useApartmentsState } from "../../contexts/ApartmentsContext";
import { ApartmentCard } from "./ApartmentCard";
import { validateApartment } from "./validation";
import { apartmentVisual, compareApartments } from "./comparison";
import type { ApartmentInput, PredictionResult } from "../../shared/api/types";

declare global {
  interface Window { Chart?: new (context: CanvasRenderingContext2D, config: ChartConfig) => { destroy: () => void }; }
}
interface ChartConfig {
  type: "line";
  data: { labels: number[]; datasets: { label: string; data: (number | null)[]; borderColor: string; backgroundColor: string; tension: number; pointBackgroundColor: string; pointRadius: number; pointHoverRadius: number; pointStyle: string; borderDash: number[]; borderWidth: number; fill: boolean }[] };
  options: { responsive: boolean; maintainAspectRatio: boolean; layout: { padding: { top: number } }; interaction: { mode: "nearest"; intersect: boolean }; plugins: { legend: { position: "bottom"; labels: { color: string; usePointStyle: boolean; font: { size: number } } }; tooltip: { callbacks: { label: (context: { dataset: { label: string }; parsed: { y: number }; dataIndex: number }) => string } }; datalabels: { display?: boolean; color?: string; anchor?: "end"; align?: "top"; offset?: number; font?: { size: number; weight: "bold" }; formatter?: (value: number) => string; hover?: { color: string; font: { size: number; weight: "bold" } } } }; scales: { x: { title: { display: boolean; text: string }; ticks: { color: string }; grid: { color: string } }; y: { title: { display: boolean; text: string; color: string }; ticks: { color: string }; grid: { color: string } } } };
}

const money = (rubles: number) => `${Math.round(rubles).toLocaleString("ru-RU")} ₽`;
const moneyMln = (millions: number) => money(millions * 1_000_000);
const priceInMillions = (rubles: number) => `${(rubles / 1_000_000).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} млн руб.`;
const fieldLabels: Record<string, string> = { region: "административный округ", district: "район", street: "улица", wall_material: "материал стен", year_build: "год постройки", floor: "этаж", area: "площадь", n_years: "горизонт прогноза" };
const assistantResultsKey = "prognosis-assistant-result-context";

function clearAssistantResults() {
  window.sessionStorage.removeItem(assistantResultsKey);
}

function saveAssistantResults(rows: { title: string; growth: number; startPrice: number; endPrice: number; place: number }[]) {
  window.sessionStorage.setItem(assistantResultsKey, JSON.stringify({ apartments: rows }));
}

function apartmentTitle(order: number, streetValue: string, apartments: { order: number; parameters: { street: string } }[]) {
  const street = streetValue.trim();
  if (!street) return "\u041d\u043e\u0432\u0430\u044f \u043a\u0432\u0430\u0440\u0442\u0438\u0440\u0430";
  const normalizedStreet = street.toLocaleLowerCase("ru-RU");
  const matching = apartments.filter((item) => item.parameters.street.trim().toLocaleLowerCase("ru-RU") === normalizedStreet);
  if (matching.length < 2) return `\u041a\u0432\u0430\u0440\u0442\u0438\u0440\u0430 \u043d\u0430 \u0443\u043b. ${street}`;
  const duplicateNumber = matching.findIndex((item) => item.order === order) + 1;
  return `\u041a\u0432\u0430\u0440\u0442\u0438\u0440\u0430 \u2116${duplicateNumber || order} \u043d\u0430 \u0443\u043b. ${street}`;
}

function apartmentFingerprint(parameters: ApartmentInput) {
  const normalizedNumber = (value: string | number | null | undefined) => Number(String(value ?? "").replace(",", ".").trim());
  return JSON.stringify([
    parameters.region.trim().toLocaleLowerCase("ru-RU"),
    parameters.district.trim().toLocaleLowerCase("ru-RU"),
    parameters.street.trim().toLocaleLowerCase("ru-RU"),
    parameters.wall_material.trim().toLocaleLowerCase("ru-RU"),
    normalizedNumber(parameters.year_build),
    normalizedNumber(parameters.floor),
    normalizedNumber(parameters.area),
  ]);
}

function parameterSignature(apartments: { id: string; parameters: object }[]) {
  return JSON.stringify(apartments.map(({ id, parameters }) => [id, parameters]));
}

const chartOptions = (label: string, years: number[], showDataLabels = true): ChartConfig["options"] => ({
  responsive: true,
  maintainAspectRatio: false,
  layout: { padding: { top: 30 } },
  interaction: { mode: "nearest", intersect: false },
  plugins: {
    legend: { position: "bottom", labels: { color: "#0f172a", usePointStyle: true, font: { size: 13 } } },
    tooltip: { callbacks: { label: (item) => ` ${item.dataset.label}: ${item.parsed.y.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} млн руб. (${years[item.dataIndex]} г.)` } },
    datalabels: showDataLabels
      ? { color: label, anchor: "end", align: "top", offset: 6, font: { size: 12, weight: "bold" }, formatter: (value) => value.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }), hover: { color: "#0f172a", font: { size: 18, weight: "bold" } } }
      : { display: false },
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
            const visual = apartmentVisual(item.order);
            const points = new Map(item.result.forecast_exact?.map((point) => [point.year, point.price_mln] as [number, number])
              ?? item.result.forecast.map((point) => [point.Год, point["Прогноз цены, млн руб."]] as [number, number]));
            if (item.result.base_year <= comparison.years[0]) points.set(item.result.base_year, (item.result.base_price_exact ?? item.result.base_price) / 1_000_000);
            return { label: item.title, data: comparison.years.map((year) => points.get(year) ?? null), borderColor: visual.color, backgroundColor: visual.color, pointBackgroundColor: visual.color, pointStyle: visual.marker, borderDash: visual.lineDash, tension: 0.25, pointRadius: 5, pointHoverRadius: 7, borderWidth: 2.5, fill: false };
          }),
        },
        options: chartOptions("#1a4fa0", comparison.years, false),
      });
    }, 100);
    return () => { window.clearInterval(timer); chart?.destroy(); };
  }, [comparison.years, results]);

  if (comparison.rows.length < 2) return <p>Для сравнения недостаточно полных прогнозов.</p>;
  const ranked = [...comparison.rows].sort((a, b) => a.place - b.place || a.order - b.order);
  return <div className="card comparison-container">
    <h2 className="card-title">Сравнительный анализ</h2>
    <p>Общий период: {comparison.years[0]}–{comparison.years.at(-1)} гг.</p>
    <h3>Сравнительная таблица прогнозов по годам</h3>
    <div className="table-wrap"><table className="forecast-table comparison-forecast-table">
      <thead><tr><th rowSpan={2}>Год</th>{results.map((item) => <th key={item.id}><span className="apartment-color-key" style={{ backgroundColor: apartmentVisual(item.order).color }} />{item.title}</th>)}<th rowSpan={2}>Инфляция, %</th></tr>
        <tr>{results.map((item) => <th key={`${item.id}-price`}>Прогноз цены, млн руб.</th>)}</tr>
      </thead>
      <tbody>{comparison.years.map((year) => <tr key={year}><td>{year}</td>{results.map((item) => {
        const point = item.result.forecast.find((forecast) => forecast.Год === year);
        return <td key={`${item.id}-${year}-price`}>{point?.["Прогноз цены, млн руб."].toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? "—"}</td>;
      })}
        <td>{results[0]?.result.forecast.find((forecast) => forecast.Год === year)?.["Инфляция, %"].toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) ?? "—"}</td>
      </tr>)}</tbody>
    </table></div>
    <h3>Общий прогноз</h3><div className="chart-wrap comparison-chart"><canvas ref={canvasRef} /></div>
    <h3>Сравнение потенциала роста квартир</h3>
    <div className="table-wrap"><table className="forecast-table"><thead><tr><th>Место</th><th>Улица</th><th>Начальная стоимость</th><th>Конечная стоимость</th><th>Прирост</th><th>Рост, %</th></tr></thead><tbody>
      {ranked.map((row) => {
        return <tr key={row.id}><td>{row.place}</td><td><span className="apartment-color-key" style={{ backgroundColor: apartmentVisual(row.order).color }} />{row.title}</td><td>{moneyMln(row.startPrice)}</td><td>{moneyMln(row.endPrice)}</td><td>{moneyMln(row.change)}</td><td>{row.growth.toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</td></tr>;
      })}
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
      const visual = apartmentVisual(order);
      chart = new Chart(canvas.getContext("2d")!, {
        type: "line",
        data: { labels: result.forecast.map((point) => point.Год), datasets: [{ label: title, data: result.forecast.map((point) => point["Прогноз цены, млн руб."]), borderColor: visual.color, backgroundColor: "rgba(37, 99, 235, 0.12)", pointBackgroundColor: visual.color, pointStyle: visual.marker, borderDash: visual.lineDash, tension: 0.25, pointRadius: 5, pointHoverRadius: 7, borderWidth: 2.5, fill: true }] },
        options: chartOptions(visual.color, result.forecast.map((point) => point.Год)),
      });
    }, 100);
    return () => { window.clearInterval(timer); chart?.destroy(); };
  }, [order, result, title]);
  return <div className="chart-wrap"><canvas ref={canvasRef} /></div>;
}

export function ApartmentWorkspace() {
  const { apartments } = useApartmentsState();
  const { addApartment, replaceApartmentsFromAssistant, appendApartmentsFromAssistant, removeApartment, updateApartmentParameters, setApartmentPrediction, setApartmentPredictions, setApartmentError, startApartmentPrediction, cancelApartmentPrediction, resetApartments, toggleApartmentCollapsed, setApartmentsCollapsed } = useApartmentsActions();
  const referenceQuery = useQuery({
    queryKey: ["reference"],
    queryFn: ({ signal }) => getReference(signal),
    retry: false,
    refetchInterval: (query) => query.state.data ? false : 1000,
    refetchIntervalInBackground: true,
  });
  const initialized = useRef(false);
  const requestController = useRef<AbortController | null>(null);
  const apartmentsRef = useRef(apartments);
  apartmentsRef.current = apartments;
  const requestVersion = useRef(0);
  const pendingIds = useRef<string[]>([]);
  const pendingAssistantPrediction = useRef<{ ids: string[]; signature: string; predictAll: boolean } | null>(null);
  const predictRef = useRef<(id?: string) => Promise<void>>(async () => undefined);
  const [activeResultId, setActiveResultId] = useState<string | "comparison">("comparison");
  const [comparisonSnapshot, setComparisonSnapshot] = useState<string | null>(null);

  useEffect(() => { if (!initialized.current) { initialized.current = true; addApartment(); } }, [addApartment]);
  useEffect(() => () => { requestVersion.current += 1; requestController.current?.abort(); }, []);
  const currentSignature = parameterSignature(apartments);
  const resultItems = apartments.filter((item) => item.prediction).map((item) => ({ id: item.id, order: item.order, title: apartmentTitle(item.order, item.parameters.street, apartments), result: item.prediction! }));
  const calculating = apartments.some((item) => item.isCalculating);
  const comparisonReady = !calculating && apartments.length > 1 && apartments.every((item) => item.prediction && !item.isPredictionStale) && comparisonSnapshot === currentSignature;
  const comparisonResults = comparisonReady ? resultItems : [];

  const invalidatePending = () => {
    requestVersion.current += 1;
    requestController.current?.abort();
    requestController.current = null;
    pendingIds.current.forEach((id) => cancelApartmentPrediction(id));
    pendingIds.current = [];
  };
  const addApartmentWithSharedHorizon = () => {
    if (calculating) return;
    invalidatePending();
    clearAssistantResults();
    addApartment({ region: "", district: "", street: "", wall_material: "", year_build: "", floor: "", area: "", n_years: apartments[0]?.parameters.n_years ?? "" });
    setComparisonSnapshot(null);
  };
  const removeApartmentSafely = (id: string) => {
    if (calculating) return;
    invalidatePending();
    clearAssistantResults();
    const remaining = apartments.filter((item) => item.id !== id);
    removeApartment(id);
    setComparisonSnapshot(null);
    if (activeResultId === id) setActiveResultId(remaining.length > 1 ? "comparison" : remaining[0]?.id ?? "comparison");
  };
  const updateParameters = (id: string, patch: Partial<(typeof apartments)[number]["parameters"]>) => {
    if (calculating) return;
    invalidatePending();
    clearAssistantResults();
    if (id === apartments[0]?.id && patch.n_years !== undefined) {
      updateApartmentParameters(id, patch);
      apartments.filter((apartment) => apartment.id !== id).forEach((apartment) => updateApartmentParameters(apartment.id, { n_years: patch.n_years }));
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
  const resetAll = () => {
    invalidatePending();
    clearAssistantResults();
    resetApartments();
    setComparisonSnapshot(null);
    setActiveResultId("comparison");
  };

  const predict = async (onlyId?: string) => {
    if (requestController.current) return;
    const selectedApartments = onlyId ? apartments.filter((item) => item.id === onlyId) : apartments;
    const reference = referenceQuery.data;
    if (!selectedApartments.length || !reference) return;
    const validation = selectedApartments.map((apartment) => ({ apartment, errors: validateApartment(apartment.parameters, reference) }));
    if (validation.some(({ errors }) => Object.keys(errors).length > 0)) {
      validation.forEach(({ apartment, errors }) => {
        const first = Object.entries(errors)[0];
        if (first) setApartmentError(apartment.id, `Квартира №${apartment.order}, поле «${fieldLabels[first[0]] ?? first[0]}»: ${first[1]}`);
        else setApartmentError(apartment.id, null);
      });
      return;
    }
    if (!onlyId && selectedApartments.length > 1) {
      const firstIdBySignature = new Map<string, string>();
      const duplicateIds = new Set<string>();
      for (const apartment of selectedApartments) {
        const fingerprint = apartmentFingerprint(apartment.parameters);
        const firstId = firstIdBySignature.get(fingerprint);
        if (firstId) {
          duplicateIds.add(firstId);
          duplicateIds.add(apartment.id);
        } else firstIdBySignature.set(fingerprint, apartment.id);
      }
      if (duplicateIds.size) {
        selectedApartments.forEach((apartment) => {
          if (duplicateIds.has(apartment.id)) setApartmentError(apartment.id, "Параметры квартир совпадают, исправьте или удалите квартиру");
        });
        return;
      }
    }

    const version = ++requestVersion.current;
    const controller = new AbortController();
    requestController.current = controller;
    pendingIds.current = selectedApartments.map((item) => item.id);
    pendingIds.current.forEach((id) => startApartmentPrediction(id));
    const submittedSignature = parameterSignature(selectedApartments);
    const commonHorizon = apartments[0]?.parameters.n_years || "5";
    try {
      if (onlyId) {
        const apartment = selectedApartments[0]!;
        const result = await predictApartment({ ...apartment.parameters, area: String(apartment.parameters.area).replace(",", ".") }, controller.signal);
        if (version !== requestVersion.current || submittedSignature !== parameterSignature(apartmentsRef.current)) return;
        setApartmentPrediction(apartment.id, result);
        const forecast = result.forecast_exact?.map((point) => point.price_mln) ?? result.forecast.map((point) => point["Прогноз цены, млн руб."]);
        const startPrice = (result.base_price_exact ?? result.base_price) / 1_000_000;
        const endPrice = forecast.at(-1) ?? startPrice;
        saveAssistantResults([{
          title: apartmentTitle(apartment.order, apartment.parameters.street, apartments),
          growth: startPrice > 0 ? (endPrice - startPrice) / startPrice * 100 : 0,
          startPrice, endPrice, place: 1,
        }]);
        setActiveResultId(apartment.id);
      } else {
        const input = selectedApartments.map((apartment) => ({
          ...apartment.parameters,
          area: String(apartment.parameters.area).replace(",", "."),
          n_years: commonHorizon,
          client_id: apartment.id,
        }));
        const response = await predictApartments(input, controller.signal);
        if (version !== requestVersion.current || submittedSignature !== parameterSignature(apartmentsRef.current)) return;
        const mapped = selectedApartments.map((apartment) => {
          const matches = response.results.filter((item) => item.client_id === apartment.id);
          if (matches.length !== 1) throw new Error(`Сервер вернул неверное количество результатов для квартиры №${apartment.order}.`);
          return { id: apartment.id, prediction: matches[0]!.prediction };
        });
        if (response.results.length !== selectedApartments.length) throw new Error("Сервер вернул неполный набор прогнозов.");
        const comparison = compareApartments(mapped.map(({ id, prediction }) => {
          const apartment = selectedApartments.find((item) => item.id === id)!;
          return { id, order: apartment.order, title: apartmentTitle(apartment.order, apartment.parameters.street, selectedApartments), result: prediction };
        }));
        saveAssistantResults(comparison.rows.map(({ title, growth, startPrice, endPrice, place }) => ({ title, growth, startPrice, endPrice, place })));
        setApartmentPredictions(mapped);
        setComparisonSnapshot(currentSignature);
        setActiveResultId(selectedApartments.length > 1 ? "comparison" : selectedApartments[0]!.id);
      }
      setApartmentsCollapsed(true);
    } catch (error) {
      if (controller.signal.aborted || version !== requestVersion.current) return;
      if (!onlyId) setComparisonSnapshot(null);
      selectedApartments.forEach((apartment) => setApartmentError(apartment.id, `Квартира №${apartment.order}: ${error instanceof Error ? error.message : "Не удалось выполнить прогноз."}`));
    } finally {
      if (version === requestVersion.current) {
        requestController.current = null;
        pendingIds.current = [];
      }
    }
  };
  predictRef.current = predict;

  useEffect(() => {
    const pending = pendingAssistantPrediction.current;
    if (!pending) return;
    const selected = pending.ids.map((id) => apartments.find((item) => item.id === id));
    if (selected.some((item) => !item)) return;
    const ready = selected as NonNullable<(typeof selected)[number]>[];
    if (parameterSignature(ready) !== pending.signature) return;
    pendingAssistantPrediction.current = null;
    void predictRef.current(pending.predictAll ? undefined : ready[0]!.id);
  }, [apartments]);

  useEffect(() => {
    const assistantFieldNames: Record<string, string> = { region: "административный округ", district: "район", street: "улица", wall_material: "материал стен", year_build: "год постройки", floor: "этаж", area: "площадь", n_years: "горизонт прогноза" };
    const handleAssistantCalculation: EventListener = (event) => {
      const detail = (event as CustomEvent<unknown>).detail;
      if (detail === null || typeof detail !== "object") {
        window.dispatchEvent(new CustomEvent("prognosis:assistant-error", { detail: "Агент передал некорректные параметры квартиры." }));
        return;
      }
      const envelope = detail as Record<string, unknown>;
      const data = Array.isArray(envelope.apartments)
        ? envelope.apartments
        : [envelope];
      if (!data.length || data.some((item) => item === null || typeof item !== "object" || Array.isArray(item))) {
        window.dispatchEvent(new CustomEvent("prognosis:assistant-error", { detail: "Агент передал некорректный список квартир." }));
        return;
      }
      const first = apartmentsRef.current[0];
      const reference = referenceQuery.data;
      if (!first || !reference) {
        window.dispatchEvent(new CustomEvent("prognosis:assistant-error", { detail: "Справочники ещё загружаются. Попробуйте повторить запрос." }));
        return;
      }
      const candidates: ApartmentInput[] = [];
      for (const item of data as Record<string, unknown>[]) {
        const textValue = (key: string) => item[key] === undefined || item[key] === null ? "" : String(item[key]);
        const candidate: ApartmentInput = {
          region: textValue("region"), district: textValue("district"), street: textValue("street"),
          wall_material: textValue("wall_material"), year_build: textValue("year_build"),
          floor: textValue("floor"), area: textValue("area"), n_years: textValue("n_years"),
        };
        const errors = validateApartment(candidate, reference);
        const firstError = Object.entries(errors)[0];
        if (firstError) {
          const message = `Квартира №${candidates.length + 1}, параметр «${assistantFieldNames[firstError[0]] ?? firstError[0]}»: ${firstError[1]}`;
          window.dispatchEvent(new CustomEvent("prognosis:assistant-error", { detail: message }));
          return;
        }
        candidates.push(candidate);
      }

      invalidatePending();
      pendingAssistantPrediction.current = null;
      window.dispatchEvent(new Event("prognosis:show-forecast"));
      const ids = envelope.operation === "append"
        ? appendApartmentsFromAssistant(candidates)
        : replaceApartmentsFromAssistant(candidates);
      const inserted = ids.map((id, index) => ({ id, parameters: candidates[index]! }));
      pendingAssistantPrediction.current = { ids, signature: parameterSignature(inserted), predictAll: envelope.operation === "append" || candidates.length > 1 };
      setComparisonSnapshot(null);
      setActiveResultId(ids.length > 1 ? "comparison" : ids[0]!);
    };
    window.addEventListener("prognosis:assistant-calculation", handleAssistantCalculation);
    return () => window.removeEventListener("prognosis:assistant-calculation", handleAssistantCalculation);
  }, [referenceQuery.data, replaceApartmentsFromAssistant, appendApartmentsFromAssistant]);

  if (!referenceQuery.data) return <section className="card" role="status">Модель и справочники загружаются…</section>;
  return <>
    <div className="workspace-heading"><button type="button" className="btn btn-secondary" onClick={resetAll}>Сбросить всё</button></div>
    <section className="apartment-list" aria-label="Квартиры для прогнозирования">
      {apartments.map((item) => <ApartmentCard key={`${item.id}-${item.formRevision}`} id={item.id} order={item.order} apartmentCount={apartments.length} isFirstApartment={item.id === apartments[0]?.id} title={apartmentTitle(item.order, item.parameters.street, apartments)} parameters={item.parameters} reference={referenceQuery.data!} collapsed={item.isCollapsed} calculating={item.isCalculating} predictionStale={item.isPredictionStale} error={item.error} onToggleCollapsed={toggleApartmentCollapsed} onRemove={removeApartmentSafely} onAdd={addApartmentWithSharedHorizon} onPredict={() => void predict(item.id)} onParameterChange={updateParameters} />)}
    </section>
    {apartments[0]?.isCollapsed && <button type="button" className="btn btn-secondary" disabled={calculating} onClick={addApartmentWithSharedHorizon}>+ Добавить квартиру</button>}
    {apartments.length > 1 && <div className="form-actions batch-actions"><button type="button" className="btn btn-primary" disabled={calculating} onClick={() => void predict()}>{calculating ? "Расчёт…" : "Рассчитать прогноз для всех квартир"}</button></div>}
    {apartments.some((item) => item.prediction) && <>
      <nav className="result-tabs" aria-label="Результаты квартир" role="tablist">
        {apartments.length > 1 && <button type="button" role="tab" aria-selected={activeResultId === "comparison"} className={`result-tab ${activeResultId === "comparison" ? "active" : ""}`} onClick={() => setActiveResultId("comparison")}>Сравнительный анализ</button>}
        {apartments.map((item) => <button key={item.id} type="button" role="tab" aria-selected={activeResultId === item.id} className={`result-tab ${activeResultId === item.id ? "active" : ""}`} onClick={() => setActiveResultId(item.id)}>{apartmentTitle(item.order, item.parameters.street, apartments)}</button>)}
      </nav>
      {activeResultId === "comparison" && apartments.length > 1
        ? comparisonReady ? <ApartmentComparison results={comparisonResults} /> : <section className="card comparison-placeholder"><h2 className="card-title">Сравнительный анализ</h2><p>Состав или параметры квартир изменились. Рассчитайте прогноз для всех квартир, чтобы обновить сравнение.</p></section>
        : (() => {
          const apartment = apartments.find((entry) => entry.id === activeResultId) || apartments.find((entry) => entry.prediction) || apartments[0]!;
          if (!apartment.prediction) return <section className="card result-card"><h2 className="card-title">Прогноз: {apartmentTitle(apartment.order, apartment.parameters.street, apartments)}</h2><p>Для этой квартиры ещё нет прогноза.</p></section>;
          const item = resultItems.find((entry) => entry.id === apartment.id)!;
          return <section className="card result-card">{apartment.isPredictionStale && <p className="comparison-note" role="status">Параметры изменились — показан устаревший прогноз. Пересчитайте квартиры.</p>}<h2 className="card-title">Прогноз: {apartmentTitle(apartment.order, apartment.parameters.street, apartments)}</h2><p>{item.result.apartment.region}, {item.result.apartment.district} · {item.result.apartment.area} м² · {item.result.apartment.floor} этаж · {item.result.apartment.year_build} г. · {item.result.apartment.wall_material}</p><div className="result-summary"><div className="summary-item"><div className="label">Базовая оценка ({item.result.base_year} г.)</div><div className="value">{priceInMillions(item.result.base_price)}</div></div><div className="summary-item"><div className="label">Коэффициент округа</div><div className="value">{item.result.coef_region.toFixed(3)}</div></div><div className="summary-item"><div className="label">Прогноз инфляции</div><div className="value">{item.result.infl_first?.toFixed(1) ?? "—"}% → {item.result.infl_last?.toFixed(1) ?? "—"}%</div></div></div><h3>Прогноз цены по годам</h3><IndividualChart result={item.result} title={item.title} order={item.order} /><div className="table-wrap"><table className="forecast-table"><thead><tr><th>Год</th><th>Прогноз цены, млн руб.</th><th>Инфляция, %</th></tr></thead><tbody>{item.result.forecast.map((point) => <tr key={point.Год}><td>{point.Год}</td><td>{point["Прогноз цены, млн руб."].toLocaleString("ru-RU", { minimumFractionDigits: 2 })}</td><td>{point["Инфляция, %"].toLocaleString("ru-RU", { minimumFractionDigits: 1 })}</td></tr>)}</tbody></table></div></section>;
        })()}
    </>}
  </>;
}
