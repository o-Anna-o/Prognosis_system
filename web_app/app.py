# Запуск:  .venv\Scripts\python.exe web_app\app.py
# или:     start_server.bat

from __future__ import annotations

import logging
import math
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

import model as m

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("prognosis")

from agent.service import chat as agent_chat
from agent.tools import configure_predictor, configure_reference_provider

from agent.storage import init_storage, get_recent_history, save_turn

app = Flask(__name__)
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Перечитывать шаблоны при каждом запросе и не кэшировать
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# Обучение модели при старте в фоновом потоке

MODEL: m.PrognosisModel | None = None
MODEL_READY = False
MODEL_ERROR: str | None = None
REFERENCE: dict | None = None
EDA_CHARTS: dict | None = None
_state_lock = threading.Lock()  # модель обучается в фоне


def _train_in_background() -> None:
    global MODEL, MODEL_READY, MODEL_ERROR, REFERENCE, EDA_CHARTS
    try:
        log.info("Начало обучения модели...")
        model = m.train_model_cached() # если данные не менялись, модель загружается мгновенно
        reference = m.load_reference_data()
        with _state_lock:
            MODEL, REFERENCE, MODEL_READY = model, reference, True
        log.info("Модель готова: %d строк, базовый год %d",
                 len(model.model_df), model.base_year)
    except Exception as exc:  # noqa: BLE001
        with _state_lock:
            MODEL_ERROR = str(exc)
        log.exception("Ошибка обучения модели: %s", exc)
        return

    # EDA-графики считаются 1 раз и кэшируются
    try:
        eda_charts = m.compute_eda_charts(model.model_df)
        with _state_lock:
            EDA_CHARTS = eda_charts
        log.info("EDA-графики готовы (%d шт.)", len(eda_charts))
    except Exception as exc:  # noqa: BLE001
        log.exception("Ошибка генерации EDA-графиков: %s", exc)


threading.Thread(target=_train_in_background, daemon=True).start()


# Валидация входных данных

def _parse_float(value, field_name: str, minimum: float | None = None) -> float:
    try:
        val = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        raise ValueError(f"Поле «{field_name}» должно быть числом.") from None
    if not math.isfinite(val):
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
    if region not in m.OFFICIAL_DISTRICTS:
        raise ValueError("Выберите административный округ из списка.")
    if not district:
        raise ValueError("Укажите район.")
    if district not in m.OFFICIAL_DISTRICTS[region]:
        raise ValueError("Выберите район из списка выбранного округа.")
    if not street:
        raise ValueError("Укажите улицу.")
    if wall_material not in m.WALL_MATERIAL_CODES:
        raise ValueError("Выберите материал стен из списка.")

    area = _parse_float(data.get("area"), "Площадь", minimum=1.0)
    year_build = _parse_int(data.get("year_build"), "Год постройки", minimum=1800)
    floor = _parse_int(data.get("floor"), "Этаж", minimum=1)

    # Горизонт прогноза необязателен: пустое поле означает 5 лет.
    raw_n_years = data.get("n_years")
    if raw_n_years is None or str(raw_n_years).strip() == "":
        n_years = 5
    else:
        n_years = _parse_int(raw_n_years, "Горизонт прогноза", minimum=1)
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


class _PayloadValidationError(ValueError):
    """Ошибка пользовательских параметров, возвращаемая API как HTTP 400."""


def _build_prediction(
    model: m.PrognosisModel,
    payload: dict | list[dict],
    *,
    include_exact: bool = False,
) -> dict | list[dict]:
    """Получает и формирует прогноз для одной квартиры или списка квартир."""
    if isinstance(payload, list):
        return [_build_prediction(model, apartment, include_exact=include_exact) for apartment in payload]
    if not isinstance(payload, dict):
        raise _PayloadValidationError("Некорректные параметры квартиры.")

    try:
        apartment = _validate_payload(payload)
    except ValueError as exc:
        raise _PayloadValidationError(str(exc)) from exc
    n_years = apartment.pop("n_years")
    result = model.forecast(apartment, n_years)

    prediction = {
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
        "forecast": result["forecast"].to_dict(orient="records"),
    }
    if include_exact:
        prediction["base_price_exact"] = float(result["base_price"])
        prediction["forecast_exact"] = result["forecast_exact"]
    return prediction



# Маршруты

@app.route("/")
def index():
    """Отдаёт собранный React-интерфейс или его HTML-shell для сборки."""
    if (FRONTEND_DIST / "index.html").is_file():
        return send_from_directory(FRONTEND_DIST, "index.html")
    return render_template("index.html")


@app.route("/assets/<path:filename>")
def frontend_assets(filename: str):
    """Статические файлы production-сборки React."""
    return send_from_directory(FRONTEND_DIST / "assets", filename)


@app.route("/api/health")
def health():
    """Health-check: отвечает всегда, пока процесс жив (не зависит от модели)."""
    return jsonify({"ok": True})


@app.route("/api/status")
def status():
    """Статус готовности модели."""
    with _state_lock:
        ready = MODEL_READY
        error = MODEL_ERROR
        base_year = MODEL.base_year if MODEL else None
        rows = len(MODEL.model_df) if MODEL else None
    return jsonify({
        "ready": ready,
        "error": error,
        "base_year": base_year,
        "rows": rows,
    })


@app.route("/api/reference")
def reference():
    """Справочные данные для формы (округа, районы, улицы, материалы)."""
    with _state_lock:
        ref = REFERENCE
    if ref is None:
        return jsonify({"error": "Справочные данные ещё не загружены."}), 503
    return jsonify(ref)


@app.route("/api/eda")
def eda():
    """EDA-графики закономерностей цен для вкладки «Закономерности цен»."""
    with _state_lock:
        charts = EDA_CHARTS
        ready = MODEL_READY
    if not ready or charts is None:
        return jsonify({"error": "Модель ещё обучается. Попробуйте позже."}), 503
    return jsonify(charts)


@app.route("/api/predict", methods=["POST"])
def predict():
    """Прогноз стоимости квартиры на N лет."""
    with _state_lock:
        model = MODEL
        ready = MODEL_READY
    if not ready or model is None:
        return jsonify({"error": "Модель ещё обучается. Попробуйте позже."}), 503

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Некорректный JSON-запрос."}), 400

    try:
        prediction = _build_prediction(model, data)
    except _PayloadValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        log.exception("Ошибка прогноза: %s", exc)
        return jsonify({"error": f"Ошибка прогноза: {exc}"}), 500

    return jsonify(prediction)


@app.route("/api/predict/batch", methods=["POST"])
def predict_batch():
    """Строит индивидуальные прогнозы для списка квартир и общий горизонт сравнения."""
    with _state_lock:
        model = MODEL
        ready = MODEL_READY
    if not ready or model is None:
        return jsonify({"error": "Модель ещё обучается. Попробуйте позже."}), 503

    data = request.get_json(silent=True)
    if not isinstance(data, list) or not data:
        return jsonify({"error": "Ожидается непустой JSON-массив квартир."}), 400

    validated = []
    seen_client_ids: set[str] = set()
    common_horizon: int | None = None
    try:
        # Проверяем каждый объект до первого обращения к прогнозу.
        for index, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                raise _PayloadValidationError(
                    f"Квартира {index}, поле «объект»: ожидается JSON-объект."
                )
            client_id = item.get("client_id")
            if not isinstance(client_id, str) or not client_id.strip():
                raise _PayloadValidationError(
                    f"Квартира {index}, поле «client_id»: требуется уникальный идентификатор."
                )
            if client_id in seen_client_ids:
                raise _PayloadValidationError(
                    f"Квартира {index}, поле «client_id»: идентификатор повторяется."
                )
            seen_client_ids.add(client_id)
            try:
                apartment = _validate_payload(item)
            except ValueError as exc:
                message = str(exc)
                field_names = (
                    ("административный округ", "region"),
                    ("район", "district"),
                    ("улицу", "street"),
                    ("материал стен", "wall_material"),
                    ("Площадь", "area"),
                    ("Год постройки", "year_build"),
                    ("Этаж", "floor"),
                    ("Горизонт прогноза", "n_years"),
                )
                field = next(
                    (name for label, name in field_names if label.casefold() in message.casefold()),
                    "параметры квартиры",
                )
                raise _PayloadValidationError(
                    f"Квартира {index}, поле «{field}»: {exc}"
                ) from exc
            if common_horizon is None:
                common_horizon = apartment["n_years"]
            elif apartment["n_years"] != common_horizon:
                raise _PayloadValidationError(
                    f"Квартира {index}, поле «n_years»: горизонт должен совпадать у всех квартир."
                )
            validated.append((client_id, apartment))
    except _PayloadValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        # Передаём нормализованные данные существующему общему построителю прогноза.
        results = []
        for client_id, apartment in validated:
            prediction = _build_prediction(model, {
                **apartment,
                "wall_material": m.WALL_MATERIAL_NAMES[apartment["wall_material_code"]],
            }, include_exact=True)
            results.append({"client_id": client_id, "prediction": prediction})

        comparison = [
            {
                "client_id": item["client_id"],
                "forecast": item["prediction"]["forecast"],
                "forecast_exact": item["prediction"]["forecast_exact"],
            }
            for item in results
        ]
    except Exception as exc:  # noqa: BLE001
        log.exception("Ошибка пакетного прогноза: %s", exc)
        return jsonify({"error": f"Ошибка прогноза: {exc}"}), 500

    return jsonify({
        "results": results,
        "comparison": {
            "horizon_years": common_horizon,
            "base_year": results[0]["prediction"]["base_year"],
            "forecasts": comparison,
        },
    })


def _predict_for_agent(payload: dict) -> dict:
    """Call the shared prediction builder without routing through Flask."""
    with _state_lock:
        model = MODEL if MODEL_READY else None
    if model is None:
        return {"ok": False, "error": "Прогноз сейчас недоступен."}
    try:
        return _build_prediction(model, payload)
    except _PayloadValidationError:
        return {"ok": False, "error": "Проверьте параметры квартиры."}


configure_predictor(_predict_for_agent)


def _reference_for_agent() -> dict | None:
    """Передаёт агенту актуальный справочник приложения."""
    with _state_lock:
        return REFERENCE


configure_reference_provider(_reference_for_agent)



@app.post("/api/agent/chat")
def agent_chat_api():
    try:
        payload = request.get_json(silent=True) or {}
        message = payload.get("message")

        if not isinstance(message, str) or not message.strip():
            return jsonify({"error": "Введите сообщение"}), 400

        message = message.strip()

        if len(message) > 4000:
            return jsonify({"error": "Сообщение слишком длинное"}), 400

        # Загружаем историю из PostgreSQL
        init_storage()
        history = get_recent_history(limit=20)

        # Вызываем существующего агента, не меняя логику прогнозирования
        answer = agent_chat(message, history=history)

        # Сохраняем сообщения после удаления персональных данных
        save_turn(message, answer)

        return jsonify({"answer": answer})

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    except Exception:
        app.logger.exception("Ошибка обработки сообщения агента")
        return jsonify({
            "error": "Не удалось обработать сообщение"
        }), 503



if __name__ == "__main__":
    # многопоточный WSGI-сервер
    try:
        from waitress import serve
    except ImportError:
        app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
    else:
        log.info("Запуск сервера на http://127.0.0.1:5000")
        serve(app, host="127.0.0.1", port=5000, threads=8)
