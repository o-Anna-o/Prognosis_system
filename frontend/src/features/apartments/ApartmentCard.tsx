import { useState, type ChangeEvent, type FocusEvent, type ReactNode } from "react";
import type { ApartmentInput, ReferenceData } from "../../shared/api/types";
import type { ApartmentParameterPatch } from "./types";
import { validateApartment, type ApartmentField } from "./validation";
import styles from "./ApartmentCard.module.css";

interface ApartmentCardProps {
  id: string;
  order: number;
  parameters: ApartmentInput;
  reference: ReferenceData;
  onParameterChange: (id: string, patch: ApartmentParameterPatch) => void;
}

export function ApartmentCard({ id, order, parameters, reference, onParameterChange }: ApartmentCardProps) {
  const [touched, setTouched] = useState<Partial<Record<ApartmentField, boolean>>>({});
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
      onParameterChange(id, { [field]: event.currentTarget.value } as ApartmentParameterPatch);
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
    <article className={`card form-card ${styles.card}`} aria-labelledby={`${id}-title`}>
      <h2 className={`card-title ${styles.title}`} id={`${id}-title`}>Параметры квартиры {order}</h2>
      <div className="form-grid">
        <div className="form-group">
          <label htmlFor={fieldId("region")}>Административный округ *</label>
          <select id={fieldId("region")} name="region" value={parameters.region} onChange={updateText("region")} onBlur={markTouched("region")} {...fieldProps("region")}>
            <option value="">Выберите округ</option>
            {reference.regions.map((region) => <option key={region} value={region}>{region}</option>)}
          </select>
          {errorMessage("region")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("district")}>Район *</label>
          <select id={fieldId("district")} name="district" value={parameters.district} onChange={updateText("district")} onBlur={markTouched("district")} {...fieldProps("district")}>
            <option value="">Выберите район</option>
            {reference.districts.map((district) => <option key={district} value={district}>{district}</option>)}
          </select>
          {errorMessage("district")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("street")}>Улица *</label>
          <input id={fieldId("street")} name="street" value={parameters.street} placeholder="Введите улицу" autoComplete="off" onChange={updateText("street")} onBlur={markTouched("street")} {...fieldProps("street")} />
          {errorMessage("street")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("wall_material")}>Материал стен *</label>
          <select id={fieldId("wall_material")} name="wall_material" value={parameters.wall_material} onChange={updateText("wall_material")} onBlur={markTouched("wall_material")} {...fieldProps("wall_material")}>
            <option value="">Выберите материал</option>
            {reference.wall_materials.map((material) => <option key={material} value={material}>{material}</option>)}
          </select>
          {errorMessage("wall_material")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("year_build")}>Год постройки *</label>
          <input id={fieldId("year_build")} name="year_build" inputMode="numeric" value={parameters.year_build} placeholder="Введите год" onChange={updateText("year_build")} onBlur={markTouched("year_build")} {...fieldProps("year_build")} />
          {errorMessage("year_build")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("floor")}>Этаж *</label>
          <input id={fieldId("floor")} name="floor" inputMode="numeric" value={parameters.floor} placeholder="Введите этаж" onChange={updateText("floor")} onBlur={markTouched("floor")} {...fieldProps("floor")} />
          {errorMessage("floor")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("area")}>Площадь, м² *</label>
          <input id={fieldId("area")} name="area" inputMode="decimal" value={parameters.area} placeholder="Введите площадь" onChange={updateText("area")} onBlur={markTouched("area")} {...fieldProps("area")} />
          {errorMessage("area")}
        </div>
        <div className="form-group">
          <label htmlFor={fieldId("n_years")}>Горизонт прогноза, лет</label>
          <input id={fieldId("n_years")} name="n_years" inputMode="numeric" value={parameters.n_years ?? ""} placeholder="По умолчанию 5 лет" onChange={updateText("n_years")} onBlur={markTouched("n_years")} {...fieldProps("n_years")} />
          {errorMessage("n_years")}
        </div>
      </div>
    </article>
  );
}
