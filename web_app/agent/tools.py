
import json
from typing import Callable, Any

from langchain_core.tools import tool

from .knowledge import search_knowledge


_predict_callback: Callable[[dict], Any] | None = None

_reference_callback: Callable[[], dict | None] | None = None


def configure_reference_provider(callback: Callable[[], dict | None]) -> None:
    global _reference_callback
    _reference_callback = callback


def get_reference_data() -> dict | None:
    """Возвращает справочник приложения (округа, районы, улицы, материалы).

    Используется для детерминированного извлечения параметров
    из сообщения пользователя до вызова модели.
    """
    if _reference_callback is None:
        return None
    return _reference_callback()


def configure_predictor(callback: Callable[[dict], Any]) -> None:
    """Подключает существующий механизм прогнозирования."""
    global _predict_callback
    _predict_callback = callback


@tool
def search_real_estate_knowledge(query: str) -> str:
    """Ищет инструкции и проверенную информацию о работе приложения."""
    results = search_knowledge(query)

    if not results:
        return (
            "В базе знаний нет подходящей записи. "
            "Не придумывай сведения о приложении."
        )

    return json.dumps(
        results,
        ensure_ascii=False,
        default=str,
    )

@tool
def get_prediction_reference(region: str = "", district: str = "") -> str:
    """Проверяет справочник приложения: округа, районы, улицы и материалы стен.
    Если передан region, возвращает районы этого округа.
    Если передан district, возвращает улицы этого района.
    Вызывай перед выбором и проверкой параметров квартиры."""
    if _reference_callback is None:
        return "Справочник временно недоступен. Не придумывай значения."

    reference = _reference_callback()
    if not isinstance(reference, dict):
        return "Справочник ещё не загружен. Не придумывай значения."

    regions = reference.get("regions", [])
    materials = reference.get("wall_materials", [])
    region_districts = reference.get("region_districts", {})
    district_streets = reference.get("district_streets", {})
    region_names = reference.get("region_names", {})

    result = {
        "regions": regions,
        "region_names": region_names,
        "wall_materials": materials,
    }

    if region:
        if region not in regions:
            result["error"] = "Округ отсутствует в справочнике."
            return json.dumps(result, ensure_ascii=False)
        result["selected_region"] = region
        result["districts"] = region_districts.get(region, [])

    if district:
        streets = district_streets.get(district)
        if streets is None:
            result["error"] = "Район отсутствует в справочнике улиц."
            return json.dumps(result, ensure_ascii=False)
        result["selected_district"] = district
        result["streets"] = streets
        if not streets:
            # Для новых официальных районов улиц в датасете может не быть.
            result["street_note"] = (
                "Список улиц для этого района пуст. "
                "Улицу можно принять свободным текстом, но нельзя придумывать."
            )

    return json.dumps(result, ensure_ascii=False)


@tool
def predict_apartment(
    region: str,
    district: str,
    street: str,
    wall_material: str,
    year_build: int,
    floor: int,
    area: float,
    n_years: int,
) -> str:
    """
    Рассчитывает прогноз цены квартиры через существующий API приложения.

    Вызывай инструмент, когда пользователь просит рассчитать прогноз.
    wall_material должен быть названием материала стен,
    которое принимает приложение, а не произвольным кодом.
    """
    if _predict_callback is None:
        return (
            "Прогноз сейчас недоступен. "
            "Воспользуйтесь обычной формой прогноза на сайте."
        )

    payload = {
        "region": region,
        "district": district,
        "street": street,
        "wall_material": wall_material,
        "year_build": year_build,
        "floor": floor,
        "area": area,
        "n_years": n_years,
    }

    try:
        result = _predict_callback(payload)

        if isinstance(result, dict) and result.get("ok") is False:
            return (
                "Прогноз не выполнен: "
                + str(result.get("error", "проверьте параметры квартиры"))
            )

        return json.dumps(
            result,
            ensure_ascii=False,
            default=str,
        )

    except Exception:
        # Не возвращаем модели traceback, секреты или внутренние детали.
        return (
            "Не удалось выполнить прогноз. "
            "Попроси пользователя проверить введённые данные "
            "и попробовать ещё раз через обычную форму."
        )


AGENT_TOOLS = [
    search_real_estate_knowledge,
    get_prediction_reference,
    predict_apartment,
]