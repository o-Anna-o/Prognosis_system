"""Django adapter for the saved comparison-model bundle."""

from __future__ import annotations

import logging
import math
import sys
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_model: Any = None
_reference: dict | None = None
_eda_charts: dict | None = None
_load_error: str | None = None


class PayloadValidationError(ValueError):
    """Invalid client input, distinct from errors raised by model code."""

# Load the saved model bundle through the model module.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEB_APP_DIR = PROJECT_ROOT / "web_app"
if str(WEB_APP_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_APP_DIR))

import model as prognosis_model  # noqa: E402


def _ensure_loaded() -> None:
    global _model, _reference, _eda_charts, _load_error
    if _model is not None:
        return
    with _lock:
        if _model is not None:
            return
        try:
            loaded_model = prognosis_model.train_model_cached()
            reference = prognosis_model.load_reference_data()
        except Exception as exc:
            _load_error = str(exc)
            logger.exception("Failed to load the saved prognosis model")
            raise RuntimeError(_load_error) from exc
        _model, _reference = loaded_model, reference
        _load_error = None


def get_status() -> dict[str, Any]:
    try:
        _ensure_loaded()
    except Exception:
        return {"ready": False, "error": _load_error, "base_year": None, "rows": None}
    return {
        "ready": True,
        "error": None,
        "base_year": _model.base_year,
        "rows": len(_model.model_df),
    }


def get_reference() -> dict:
    _ensure_loaded()
    return _reference


def get_eda_charts() -> dict:
    _ensure_loaded()
    global _eda_charts
    if _eda_charts is None:
        with _lock:
            if _eda_charts is None:
                _eda_charts = prognosis_model.compute_eda_charts(_model.model_df)
    return _eda_charts


def _parse_float(value: Any, field_name: str, minimum: float | None = None) -> float:
    try:
        number = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        raise ValueError(f"Поле «{field_name}» должно быть числом.") from None
    if not math.isfinite(number):
        raise ValueError(f"Поле «{field_name}» должно быть числом.")
    if minimum is not None and number < minimum:
        raise ValueError(f"Поле «{field_name}» должно быть не меньше {minimum:g}.")
    return number


def _parse_int(value: Any, field_name: str, minimum: int | None = None) -> int:
    number = _parse_float(value, field_name)
    if not number.is_integer():
        raise ValueError(f"Поле «{field_name}» должно быть целым числом.")
    result = int(number)
    if minimum is not None and result < minimum:
        raise ValueError(f"Поле «{field_name}» должно быть не меньше {minimum}.")
    return result


def _validate_payload(data: Any) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Некорректные параметры квартиры.")
    region = str(data.get("region", "")).strip()
    district = str(data.get("district", "")).strip()
    street = str(data.get("street", "")).strip()
    wall_material = str(data.get("wall_material", "")).strip()
    if not region:
        raise ValueError("Выберите административный округ.")
    if region not in prognosis_model.OFFICIAL_DISTRICTS:
        raise ValueError("Выберите административный округ из списка.")
    if not district:
        raise ValueError("Укажите район.")
    if district not in prognosis_model.OFFICIAL_DISTRICTS[region]:
        raise ValueError("Выберите район из списка выбранного округа.")
    if not street:
        raise ValueError("Укажите улицу.")
    if wall_material not in prognosis_model.WALL_MATERIAL_CODES:
        raise ValueError("Выберите материал стен из списка.")

    raw_horizon = data.get("n_years")
    horizon = 5 if raw_horizon is None or str(raw_horizon).strip() == "" else _parse_int(
        raw_horizon, "Горизонт прогноза", minimum=1
    )
    if horizon > 20:
        raise ValueError("Горизонт прогноза не должен превышать 20 лет.")
    return {
        "region": region,
        "district": district,
        "street": street,
        "wall_material_code": prognosis_model.WALL_MATERIAL_CODES[wall_material],
        "year_build": _parse_int(data.get("year_build"), "Год постройки", minimum=1800),
        "floor": _parse_int(data.get("floor"), "Этаж", minimum=1),
        "area": _parse_float(data.get("area"), "Площадь квартиры, минимум 25 м²", minimum=25.0),
        "n_years": horizon,
    }


def validate_payload(data: Any) -> dict:
    try:
        return _validate_payload(data)
    except ValueError as exc:
        raise PayloadValidationError(str(exc)) from exc


def build_prediction(data: Any, *, include_exact: bool = False) -> dict:
    _ensure_loaded()
    apartment = validate_payload(data)
    horizon = apartment.pop("n_years")
    result = _model.forecast(apartment, horizon)
    prediction = {
        "apartment": {
            "region": apartment["region"],
            "district": apartment["district"],
            "street": apartment["street"],
            "wall_material": prognosis_model.WALL_MATERIAL_NAMES[apartment["wall_material_code"]],
            "year_build": apartment["year_build"],
            "floor": apartment["floor"],
            "area": apartment["area"],
        },
        "base_year": result["base_year"],
        "base_price": round(result["base_price"], 2),
        "coef_region": round(result["coef_region"], 3),
        "avg_inflation_level": result["avg_inflation_level"],
        "infl_first": result["infl_first"],
        "infl_last": result["infl_last"],
        "forecast": result["forecast"].to_dict(orient="records"),
    }
    if include_exact:
        prediction["base_price_exact"] = float(result["base_price"])
        prediction["forecast_exact"] = result["forecast_exact"]
    return prediction
