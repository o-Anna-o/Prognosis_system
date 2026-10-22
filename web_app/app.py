# Запуск:  .venv\Scripts\python.exe web_app\app.py
# или:     start_server.bat

from __future__ import annotations

import logging
import threading

from flask import Flask, jsonify, render_template, request

import model as m

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("prognosis")

from agent.service import chat as agent_chat
from agent.tools import configure_predictor, configure_reference_provider

from agent.storage import init_storage, get_recent_history, save_turn

app = Flask(__name__)

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



# Маршруты

@app.route("/")
def index():
    """Главная страница с формой."""
    return render_template("index.html")


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
        apartment = _validate_payload(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        result = model.forecast(apartment, apartment.pop("n_years"))
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


def _predict_for_agent(payload: dict) -> dict:
    """
    Использует существующий API прогноза внутри Flask,
    не обращаясь к самой себе по HTTP.
    """
    with app.test_client() as client:
        response = client.post(
            "/api/predict",
            json=payload,
        )

        try:
            result = response.get_json()
        except Exception:
            result = None

        if response.status_code >= 400:
            # Не передаём агенту внутренние подробности ошибки.
            return {
                "ok": False,
                "error": (
                    "Прогноз не выполнен. "
                    "Проверьте параметры квартиры."
                ),
            }

        if not isinstance(result, dict):
            return {
                "ok": False,
                "error": "Не удалось получить результат прогноза.",
            }

        return result


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
