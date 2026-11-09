import type { ApartmentInput, ReferenceData } from "../../shared/api/types";

export type ApartmentField = keyof ApartmentInput;
export type ApartmentFieldErrors = Partial<Record<ApartmentField, string>>;

function numberValue(value: string | number | null | undefined): number | null {
  if (value == null || String(value).trim() === "") return null;
  const parsed = Number(String(value).replace(",", ".").trim());
  return Number.isFinite(parsed) ? parsed : null;
}

export function validateApartment(
  parameters: ApartmentInput,
  reference: ReferenceData,
): ApartmentFieldErrors {
  const errors: ApartmentFieldErrors = {};
  const region = parameters.region.trim();
  const district = parameters.district.trim();
  const street = parameters.street.trim();
  const material = parameters.wall_material.trim();

  if (!region) errors.region = "Выберите административный округ.";
  else if (!reference.regions.includes(region)) errors.region = "Выберите округ из списка.";

  if (!district) errors.district = "Укажите район.";
  else if (!region || !reference.region_districts[region]?.includes(district)) {
    errors.district = "Выберите район из списка выбранного округа.";
  }

  if (!street) errors.street = "Укажите улицу.";
  if (!material) errors.wall_material = "Выберите материал стен.";
  else if (!reference.wall_materials.includes(material)) errors.wall_material = "Выберите материал из списка.";

  const area = numberValue(parameters.area);
  if (area === null) errors.area = "Площадь должна быть числом.";
  else if (area < 25) errors.area = "Площадь квартиры не может быть меньше 25 м².";

  const year = numberValue(parameters.year_build);
  if (year === null) errors.year_build = "Год постройки должен быть числом.";
  else if (!Number.isInteger(year)) errors.year_build = "Год постройки должен быть целым числом.";
  else if (year < 1800) errors.year_build = "Год постройки должен быть не меньше 1800.";

  const floor = numberValue(parameters.floor);
  if (floor === null) errors.floor = "Этаж должен быть числом.";
  else if (!Number.isInteger(floor)) errors.floor = "Этаж должен быть целым числом.";
  else if (floor < 1) errors.floor = "Этаж должен быть не меньше 1.";

  const horizonRaw = String(parameters.n_years ?? "").trim();
  if (horizonRaw) {
    const horizon = numberValue(horizonRaw);
    if (horizon === null || !Number.isInteger(horizon)) {
      errors.n_years = "Горизонт должен быть целым числом не меньше 1.";
    } else if (horizon < 1) {
      errors.n_years = "Горизонт должен быть не меньше 1 года.";
    }
  }

  return errors;
}
