# -*- coding: utf-8 -*-
"""
Запуск:  .venv\\Scripts\\python.exe web_app\\app.py
"""

from __future__ import annotations

import logging
import threading

from flask import Flask, jsonify, render_template, request

import model as m

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("prognosis")

app = Flask(__name__)

# Режим разработки: перечитывать шаблоны при каждом запросе и не кэшировать
# статику (style.css/script.js), чтобы правки сразу отображались на сайте.
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# Обучение модели при старте (в фоновом потоке, чтобы сервер поднялся сразу)

MODEL: m.PrognosisModel | None = None
MODEL_READY = False
MODEL_ERROR: str | None = None
REFERENCE: dict | None = None


def _train_in_background() -> None:
    global MODEL, MODEL_READY, MODEL_ERROR, REFERENCE
    try:
        log.info("Начало обучения модели...")
        MODEL = m.train_model()
        REFERENCE = m.load_reference_data()
        MODEL_READY = True
        log.info("Модель обучена: %d строк, базовый год %d",
                 len(MODEL.model_df), MODEL.base_year)
    except Exception as exc:  # noqa: BLE001
        MODEL_ERROR = str(exc)
        log.exception("Ошибка обучения модели: %s", exc)


threading.Thread(target=_train_in_background, daemon=True).start()



# Валидация входных данных

def _parse_float(value, field_name: str, minimum: float | None = None) -> float:
    try:
        val = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        raise ValueError(f"Поле «{field_name}» должно быть числом.") from None
    if val != val:  # NaN
        raise ValueError(f"Поле «{field_name}» должно быть числом.")
    if minimum is not None and val < minimum:
        raise ValueError(f"Поле «{field_name}» должно быть не меньше {minimum:g}.")
    return val


def _parse_int(value, field_name: str, minimum: int | None = None) -> int:
    val = _parse_float(value, field_name)
    if not float(val).is_integer():
        raise ValueError(f"Поле «{field_name}» должно быть целым числом.")
    ival = int(val)
    if minimum is not None and ival < minimum:
        raise ValueError(f"Поле «{field_name}» должно быть не меньше {minimum}.")
    return ival


def _validate_payload(data: dict) -> dict:
    """Проверка и нормализация параметров квартиры из запроса."""
    region = str(data.get("region", "")).strip()
    district = str(data.get("district", "")).strip()
    street = str(data.get("street", "")).strip()
    wall_material = str(data.get("wall_material", "")).strip()

    if not region:
        raise ValueError("Выберите административный округ.")
    if not district:
        raise ValueError("Укажите район.")
    if not street:
        raise ValueError("Укажите улицу.")
    if wall_material not in m.WALL_MATERIAL_CODES:
        raise ValueError("Выберите материал стен из списка.")

    area = _parse_float(data.get("area"), "Площадь", minimum=1.0)
    year_build = _parse_int(data.get("year_build"), "Год постройки", minimum=1800)
    floor = _parse_int(data.get("floor"), "Этаж", minimum=1)
    n_years = _parse_int(data.get("n_years", 5), "Горизонт прогноза", minimum=1)
    if n_years > 20:
        raise ValueError("Горизонт прогноза не должен превышать 20 лет.")

    return {
        "region": region,
        "district": district,
        "street": street,
        "wall_material_code": m.WALL_MATERIAL_CODES[wall_material],
        "year_build": year_build,
        "floor": floor,
        "area": area,
        "n_years": n_years,
    }



# Маршруты

@app.route("/")
def index():
    """Главная страница с формой."""
    return render_template("index.html")


@app.route("/api/status")
def status():
    """Статус готовности модели."""
    return jsonify({
        "ready": MODEL_READY,
        "error": MODEL_ERROR,
        "base_year": MODEL.base_year if MODEL else None,
        "rows": len(MODEL.model_df) if MODEL else None,
    })


@app.route("/api/reference")
def reference():
    """Справочные данные для формы (округа, районы, улицы, материалы)."""
    if REFERENCE is None:
        return jsonify({"error": "Справочные данные ещё не загружены."}), 503
    return jsonify(REFERENCE)


@app.route("/api/eda")
def eda():
    """EDA-графики закономерностей цен для вкладки «Закономерности цен»."""
    if not MODEL_READY or MODEL is None:
        return jsonify({"error": "Модель ещё обучается. Попробуйте позже."}), 503
    try:
        charts = m.compute_eda_charts(MODEL.model_df)
    except Exception as exc:  # noqa: BLE001
        log.exception("Ошибка генерации EDA-графиков: %s", exc)
        return jsonify({"error": f"Ошибка генерации EDA-графиков: {exc}"}), 500
    return jsonify(charts)


@app.route("/api/predict", methods=["POST"])
def predict():
    """Прогноз стоимости квартиры на N лет."""
    if not MODEL_READY or MODEL is None:
        return jsonify({"error": "Модель ещё обучается. Попробуйте позже."}), 503

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Некорректный JSON-запрос."}), 400

    try:
        apartment = _validate_payload(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        result = MODEL.forecast(apartment, apartment.pop("n_years"))
    except Exception as exc:  # noqa: BLE001
        log.exception("Ошибка прогноза: %s", exc)
        return jsonify({"error": f"Ошибка прогноза: {exc}"}), 500

    forecast_rows = result["forecast"].to_dict(orient="records")
    return jsonify({
        "apartment": {
            "region": apartment["region"],
            "district": apartment["district"],
            "street": apartment["street"],
            "wall_material": m.WALL_MATERIAL_NAMES[apartment["wall_material_code"]],
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
        "forecast": forecast_rows,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
