import type { ChangeEvent } from "react";
import type { ApartmentInput, ReferenceData } from "../../shared/api/types";
import type { ApartmentParameterPatch } from "./types";
import styles from "./ApartmentCard.module.css";

interface ApartmentCardProps {
  id: string;
  order: number;
  parameters: ApartmentInput;
  reference: ReferenceData;
  onParameterChange: (id: string, patch: ApartmentParameterPatch) => void;
}

export function ApartmentCard({
  id,
  order,
  parameters,
  reference,
  onParameterChange,
}: ApartmentCardProps) {
  const fieldId = (field: keyof ApartmentInput) => `${id}-${field}`;
  const updateText =
    (field: keyof ApartmentInput) =>
    (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      onParameterChange(id, { [field]: event.currentTarget.value } as ApartmentParameterPatch);
    };

  return (
    <article className={`card form-card ${styles.card}`} aria-labelledby={`${id}-title`}>
      <h2 className={`card-title ${styles.title}`} id={`${id}-title`}>
        Параметры квартиры {order}
      </h2>
      <div className="form-grid">
        <div className="form-group">
          <label htmlFor={fieldId("region")}>Административный округ *</label>
          <select id={fieldId("region")} name="region" value={parameters.region} onChange={updateText("region")}>
            <option value=""> выберите округ </option>
            {reference.regions.map((region) => <option key={region} value={region}>{region}</option>)}
          </select>
        </div>

        <div className="form-group">
          <label htmlFor={fieldId("district")}>Район *</label>
          <select id={fieldId("district")} name="district" value={parameters.district} onChange={updateText("district")}>
            <option value=""> выберите район </option>
            {reference.districts.map((district) => <option key={district} value={district}>{district}</option>)}
          </select>
        </div>

        <div className="form-group">
          <label htmlFor={fieldId("street")}>Улица *</label>
          <input id={fieldId("street")} name="street" value={parameters.street} placeholder="Введите улицу" autoComplete="off" onChange={updateText("street")} />
        </div>

        <div className="form-group">
          <label htmlFor={fieldId("wall_material")}>Материал стен *</label>
          <select id={fieldId("wall_material")} name="wall_material" value={parameters.wall_material} onChange={updateText("wall_material")}>
            <option value=""> выберите материал </option>
            {reference.wall_materials.map((material) => <option key={material} value={material}>{material}</option>)}
          </select>
        </div>

        <div className="form-group">
          <label htmlFor={fieldId("year_build")}>Год постройки *</label>
          <input id={fieldId("year_build")} name="year_build" inputMode="numeric" value={parameters.year_build} placeholder="Введите год" onChange={updateText("year_build")} />
        </div>

        <div className="form-group">
          <label htmlFor={fieldId("floor")}>Этаж *</label>
          <input id={fieldId("floor")} name="floor" inputMode="numeric" value={parameters.floor} placeholder="Введите этаж" onChange={updateText("floor")} />
        </div>

        <div className="form-group">
          <label htmlFor={fieldId("area")}>Площадь, м² *</label>
          <input id={fieldId("area")} name="area" inputMode="decimal" value={parameters.area} placeholder="Введите площадь" onChange={updateText("area")} />
        </div>

        <div className="form-group">
          <label htmlFor={fieldId("n_years")}>Горизонт прогноза, лет</label>
          <input id={fieldId("n_years")} name="n_years" inputMode="numeric" value={parameters.n_years ?? ""} placeholder="Введите число лет (по умолчанию 5)" onChange={updateText("n_years")} />
        </div>
      </div>
    </article>
  );
}
