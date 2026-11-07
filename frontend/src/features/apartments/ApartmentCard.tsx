import { useState, type ChangeEvent, type FocusEvent, type ReactNode } from "react";
import type { ApartmentInput, ReferenceData } from "../../shared/api/types";
import type { ApartmentParameterPatch } from "./types";
import { validateApartment, type ApartmentField } from "./validation";
import styles from "./ApartmentCard.module.css";

interface ApartmentCardProps {
  id: string;
  order: number;
  apartmentCount: number;
  isFirstApartment: boolean;
  title: string;
  parameters: ApartmentInput;
  reference: ReferenceData;
  collapsed: boolean;
  calculating: boolean;
  predictionStale: boolean;
  error: string | null;
  onToggleCollapsed: (id: string) => void;
  onRemove: (id: string) => void;
  onAdd: () => void;
  onPredict: (id: string) => void;
  onParameterChange: (id: string, patch: ApartmentParameterPatch) => void;
}

export function ApartmentCard({ id, order, apartmentCount, isFirstApartment, title, parameters, reference, collapsed, calculating, predictionStale, error, onToggleCollapsed, onRemove, onAdd, onPredict, onParameterChange }: ApartmentCardProps) {
  const [touched, setTouched] = useState<Partial<Record<ApartmentField, boolean>>>({});
  const [horizonFocused, setHorizonFocused] = useState(false);
  const errors = validateApartment(parameters, reference);
  const fieldId = (field: ApartmentField) => `${id}-${field}`;
  const fieldError = (field: ApartmentField) => touched[field] ? errors[field] : undefined;
  const fieldProps = (field: ApartmentField) => ({
    "aria-invalid": Boolean(fieldError(field)),
    "aria-describedby": fieldError(field) ? `${fieldId(field)}-error` : undefined,
    className: fieldError(field) ? "invalid" : undefined,
  });
  const updateText = (field: ApartmentField) =>
    (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const value = event.currentTarget.value;
      if (field === "region") {
        onParameterChange(id, { region: value, district: "", street: "" });
      } else if (field === "district") {
        onParameterChange(id, { district: value, street: "" });
      } else {
        onParameterChange(id, { [field]: value } as ApartmentParameterPatch);
      }
    };
  const markTouched = (field: ApartmentField) =>
    (_event: FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
      setTouched((current) => ({ ...current, [field]: true }));
    };
  const errorMessage = (field: ApartmentField): ReactNode => {
    const message = fieldError(field);
    return <span className="error-msg" id={`${fieldId(field)}-error`} role={message ? "alert" : undefined}>{message}</span>;
  };

  return (
    <article id={`apartment-card-${order}`} className={`card form-card apartment-card ${styles.card} ${collapsed ? "collapsed" : ""}`} aria-labelledby={`${id}-title`}>
      <h2 className={`card-title ${styles.title}`} id={`${id}-title`}>{title}</h2>
      {apartmentCount > 1 && <button type="button" className="apartment-remove-btn" aria-label={`Удалить квартиру №${order}`} title="Удалить квартиру" disabled={calculating} onClick={() => onRemove(id)}>×</button>}
      {!collapsed && <>
      <div id={`${id}-fields`} className="form-grid">
        <div className="form-group">
          <label htmlFor={fieldId("region")}>Административный округ *</label>
          <select id={fieldId("region")} name="region" value={parameters.region} disabled={calculating} onChange={updateText("region")} onBlur={markTouched("region")} {...fieldProps("region")}>
            <option value="">Выберите округ</option>
            {reference.regions.map((region) => <option key={region} value={region}>{region}</option>)}
          </select>
          {errorMessage("region")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("district")}>Район *</label>
          <select id={fieldId("district")} name="district" value={parameters.district} disabled={calculating} onChange={updateText("district")} onBlur={markTouched("district")} {...fieldProps("district")}>
            <option value="">Выберите район</option>
            {(reference.region_districts[parameters.region] || []).map((district) => <option key={district} value={district}>{district}</option>)}
          </select>
          {errorMessage("district")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("street")}>Улица *</label>
          <input id={fieldId("street")} name="street" value={parameters.street} disabled={calculating} placeholder="Введите улицу" autoComplete="off" onChange={updateText("street")} onBlur={markTouched("street")} {...fieldProps("street")} />
          {errorMessage("street")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("wall_material")}>Материал стен *</label>
          <select id={fieldId("wall_material")} name="wall_material" value={parameters.wall_material} disabled={calculating} onChange={updateText("wall_material")} onBlur={markTouched("wall_material")} {...fieldProps("wall_material")}>
            <option value="">Выберите материал</option>
            {reference.wall_materials.map((material) => <option key={material} value={material}>{material}</option>)}
          </select>
          {errorMessage("wall_material")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("year_build")}>Год постройки *</label>
          <input id={fieldId("year_build")} name="year_build" inputMode="numeric" value={parameters.year_build} disabled={calculating} placeholder="Введите год" onChange={updateText("year_build")} onBlur={markTouched("year_build")} {...fieldProps("year_build")} />
          {errorMessage("year_build")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("floor")}>Этаж *</label>
          <input id={fieldId("floor")} name="floor" inputMode="numeric" value={parameters.floor} disabled={calculating} placeholder="Введите этаж" onChange={updateText("floor")} onBlur={markTouched("floor")} {...fieldProps("floor")} />
          {errorMessage("floor")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("area")}>Площадь, м² *</label>
          <input id={fieldId("area")} name="area" inputMode="decimal" value={parameters.area} disabled={calculating} placeholder="Введите площадь" onChange={updateText("area")} onBlur={markTouched("area")} {...fieldProps("area")} />
          {errorMessage("area")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("n_years")}>Горизонт прогноза, лет</label>
          <input id={fieldId("n_years")} name="n_years" inputMode="numeric" value={parameters.n_years ?? ""} disabled={calculating} readOnly={!isFirstApartment} placeholder="По умолчанию 5 лет" onFocus={() => { if (!isFirstApartment) setHorizonFocused(true); }} onClick={() => { if (!isFirstApartment) setHorizonFocused(true); }} onChange={updateText("n_years")} onBlur={(event) => { setHorizonFocused(false); markTouched("n_years")(event); }} {...fieldProps("n_years")} aria-describedby={!isFirstApartment && horizonFocused ? `${fieldId("n_years")}-note` : fieldError("n_years") ? `${fieldId("n_years")}-error` : undefined} />
          {!isFirstApartment && horizonFocused && <small id={`${fieldId("n_years")}-note`} className="shared-horizon-note">Горизонт прогноза един для всех рассматриваемых квартир. Поменять его можно в первой квартире.</small>}
          {errorMessage("n_years")}
        </div>
      </div>
      <div className="form-actions">
        {apartmentCount === 1 && <button type="button" className="btn btn-primary" disabled={calculating} onClick={() => onPredict(id)}>{calculating ? "Расчёт…" : "Рассчитать прогноз"}</button>}
        <button type="button" className="btn btn-secondary" onClick={() => onParameterChange(id, { region: "", district: "", street: "", wall_material: "", year_build: "", floor: "", area: "", n_years: "5" })}>Сбросить</button>
        {isFirstApartment && <button type="button" className="btn btn-secondary" disabled={calculating} onClick={onAdd}>+ Добавить квартиру</button>}
      </div>
      {predictionStale && <p role="status">Параметры изменены — прогноз устарел. Рассчитайте его снова.</p>}
      {error && <p className="error-msg" role="alert">{error}</p>}
      </>}
      <button type="button" id={order === 1 ? "toggle-params-btn" : `toggle-params-btn-${order}`} className={`collapse-btn ${collapsed ? "collapsed-toggle" : "expanded-toggle"}`} aria-expanded={!collapsed} aria-label={collapsed ? "Развернуть параметры квартиры" : "Свернуть параметры квартиры"} onClick={() => onToggleCollapsed(id)}>▲</button>
    </article>
  );
}
