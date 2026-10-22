
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain_ollama import ChatOllama

from .tools import AGENT_TOOLS, get_reference_data


BASE_DIR = Path(__file__).resolve().parent.parent
PROMPT_PATH = BASE_DIR / "prompts" / "prognosis_system.txt"

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://127.0.0.1:11434",
)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")


def load_system_prompt() -> str:
    """Читает системные инструкции агента."""
    return PROMPT_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def get_agent():
    """Создаёт агента один раз на процесс приложения."""
    model = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
        # qwen3 по умолчанию генерирует блок «размышлений», который
        # съедал весь лимит токенов, и ответ обрезался пустым.
        reasoning=False,
        num_predict=2048,
    )

    return create_agent(
        model=model,
        tools=AGENT_TOOLS,
        system_prompt=load_system_prompt(),
    )


REQUIRED_PARAMS = [
    "region",
    "district",
    "street",
    "wall_material",
    "year_build",
    "floor",
    "area",
]

PARAM_LABELS = {
    "region": "административный округ",
    "district": "район",
    "street": "улица",
    "wall_material": "материал стен",
    "year_build": "год постройки",
    "floor": "этаж квартиры",
    "area": "площадь квартиры",
}

# Примеры значений, чтобы пользователь понимал, что именно нужно ввести.
PARAM_HINTS = {
    "region": "например, ВАО",
    "district": "например, Восточное Измайлово",
    "street": "например, Первомайская",
    "wall_material": "например, Крупнопанельные",
    "year_build": "например, 1969",
    "floor": "например, 7",
    "area": "например, 60",
}

FORECAST_KEYWORDS = (
    "спрогноз",
    "прогноз",
    "рассчита",
    "расчёт",
    "расчет",
    "посчита",
    "оцени",
    "оценк",
    "стоимост",
    "цену",
    "цена",
    "цены",
    "сколько стоит",
    "сколько будет стоить",
    "предскаж",
)


def _normalize(value: str) -> str:
    """Приводит текст к виду для сравнения: нижний регистр, без «ё»."""
    return re.sub(r"\s+", " ", str(value).lower().replace("ё", "е")).strip()


def _contains_word(text: str, candidate: str) -> bool:
    """Ищет название как отдельное слово, а не часть другого слова."""
    pattern = r"(?<!\w)" + re.escape(candidate) + r"(?!\w)"
    return re.search(pattern, text) is not None


def _matches(text: str, candidate: str) -> bool:
    """Проверяет вхождение названия, в том числе в обратном порядке слов."""
    if _contains_word(text, candidate):
        return True
    words = candidate.split()
    if len(words) == 2 and _contains_word(text, f"{words[1]} {words[0]}"):
        return True
    return False


def _extract_street_phrase(text: str) -> str:
    """Извлекает улицу после слов «улица», «проспект», «переулок» и т. п.

    Нужен для новых официальных районов, которых может не быть в списке
    улиц датасета. Это не придумывание: берётся текст пользователя.
    """
    pattern = (
        r"(?:улица|ул\.?|проспект|пр-т|пр\.?|переулок|пер\.?|шоссе|бульвар|"
        r"набережная|проезд|аллея)\s+([^,;]+)"
    )
    match = re.search(pattern, text)
    if not match:
        return ""

    value = match.group(1)
    for stop_word in ("материал", "площадь", "год", "этаж", "район", "округ"):
        value = re.split(rf"\b{stop_word}\b", value, maxsplit=1)[0]

    value = value.strip(" .,;:-")
    if not value or len(value) > 60:
        return ""

    return value[:1].upper() + value[1:]


def _fallback_reference() -> dict[str, Any]:
    """Минимальный справочник из констант модели.

    Нужен, пока основной справочник ещё не загружен (модель обучается),
    чтобы агент не спрашивал заново уже указанные округ, район и материал.
    """
    try:
        from model import (  # локальный импорт, чтобы не было цикла
            DISTRICT_DATASET_ALIASES,
            OFFICIAL_DISTRICTS,
            REGION_ALIASES,
            REGION_NAMES,
            WALL_MATERIAL_ALIASES,
            WALL_MATERIAL_NAMES,
        )
    except Exception:  # noqa: BLE001
        return {}

    return {
        "regions": sorted(OFFICIAL_DISTRICTS),
        "districts": sorted(
            {district for items in OFFICIAL_DISTRICTS.values() for district in items}
        ),
        "streets": [],
        "region_districts": {
            region: list(districts)
            for region, districts in OFFICIAL_DISTRICTS.items()
        },
        "district_streets": {},
        "wall_materials": list(WALL_MATERIAL_NAMES.values()),
        "region_names": REGION_NAMES,
        "region_aliases": REGION_ALIASES,
        "district_aliases": DISTRICT_DATASET_ALIASES,
        "wall_material_aliases": WALL_MATERIAL_ALIASES,
    }


def _extract_parameters(message: str) -> dict[str, Any]:
    """Детерминированно извлекает параметры квартиры из текста сообщения."""
    params: dict[str, Any] = {}
    text = _normalize(message)

    # n_years — горизонт прогноза: «горизонт прогноза 5 лет», «на 5 лет», «5 лет»
    m = re.search(
        r"горизонт(?:\s+прогноза)?\s+(?:на\s+)?(\d{1,2})\s*(?:лет|год(?:а|ов)?|г\.?)",
        text,
    )
    if not m:
        m = re.search(r"(?:на\s+)?(\d{1,2})\s+лет", text)
    if m:
        value = int(m.group(1))
        if 1 <= value <= 20:
            params["n_years"] = value

    # year_build — «год постройки 1969», «построена в 1969», «1969 года»
    m = re.search(
        r"(?:год(?:\s+постройки)?|постройк\w*|построен(?:а|о)?\s+в)\s*[:\s-]*(\d{4})",
        text,
    )
    if not m:
        m = re.search(r"(\d{4})\s*(?:года?|г\.?)", text)
    if m:
        value = int(m.group(1))
        if 1800 <= value <= 2100:
            params["year_build"] = value
    if "year_build" not in params:
        # Отдельно стоящий четырёхзначный год: «... 1969, этаж 7».
        m = re.search(r"(?<!\d)(\d{4})(?!\d)", text)
        if m:
            value = int(m.group(1))
            if 1800 <= value <= 2100:
                params["year_build"] = value

    # floor — «этаж 7», «7 этаж», «на 7-м этаже»
    m = re.search(r"этаж(?:е)?\s*[:\s-]*(\d{1,2})", text)
    if not m:
        m = re.search(r"(\d{1,2})\s*(?:-?[а-я]+)?\s*этаж(?!\w)", text)
    if m:
        value = int(m.group(1))
        if value >= 1:
            params["floor"] = value

    # area — «площадь 60», «60 м²», «60 кв. м», «60 метров»
    m = re.search(
        r"(?:площадь(?:ю)?|кв\.?\s*м|м²|м2)\s*[:\s-]*(\d{1,4}(?:[.,]\d+)?)",
        text,
    )
    if not m:
        m = re.search(
            r"(\d{1,4}(?:[.,]\d+)?)\s*"
            r"(?:кв\.?\s*м|м²|м2|кв\.?\s*метр\w*|метр\w*)",
            text,
        )
    if m:
        value = float(m.group(1).replace(",", "."))
        if value > 0:
            params["area"] = value

    reference = get_reference_data() or _fallback_reference()

    # Материал стен: официальное название или разговорный вариант.
    best_material = None
    best_len = 0
    for material in reference.get("wall_materials", []):
        candidate = _normalize(material)
        if len(candidate) > best_len and candidate in text:
            best_material = material
            best_len = len(candidate)
    if best_material is None:
        aliases = reference.get("wall_material_aliases", {})
        for alias, material in sorted(
            aliases.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if _normalize(alias) in text:
                best_material = material
                break
    if best_material:
        params["wall_material"] = best_material

    # Округ: код («ВАО») или полное название.
    best_region = None
    best_len = 0
    for region in reference.get("regions", []):
        candidate = _normalize(region)
        if len(candidate) > best_len and candidate in text:
            best_region = region
            best_len = len(candidate)
    if best_region is None:
        aliases = reference.get("region_aliases", {})
        for alias, region in sorted(
            aliases.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if _normalize(alias) in text:
                best_region = region
                break
    if best_region:
        params["region"] = best_region

    # Район: официальные названия и варианты из датасета.
    # Если округ уже известен, ищем только среди районов этого округа:
    # одинаковые названия встречаются в разных округах (например, «Внуково»).
    district_map: dict[str, str] = {}
    region_districts = reference.get("region_districts", {})
    selected_region = params.get("region")
    if selected_region and region_districts.get(selected_region):
        districts_source = {selected_region: region_districts[selected_region]}
    else:
        districts_source = region_districts

    for districts in districts_source.values():
        for district in districts:
            district_map[_normalize(district)] = district
    for official, variants in reference.get("district_aliases", {}).items():
        if selected_region and official not in districts_source.get(selected_region, []):
            continue
        for variant in variants:
            district_map.setdefault(_normalize(variant), official)

    best_district = None
    best_len = 0
    for candidate, district in district_map.items():
        if len(candidate) > best_len and _matches(text, candidate):
            best_district = district
            best_len = len(candidate)
    if best_district:
        params["district"] = best_district

    # Улица: сначала явная конструкция «улица …», затем справочник.
    street_phrase = _extract_street_phrase(text)
    if street_phrase:
        canonical_street = None
        for street in reference.get("streets", []):
            if _normalize(street) == _normalize(street_phrase):
                canonical_street = street
                break
        params["street"] = canonical_street or street_phrase
    else:
        # Самое длинное совпадение, чтобы «Нижняя Первомайская»
        # не подменялась на «Первомайская».
        excluded = {
            _normalize(params.get("district", "")),
            _normalize(params.get("region", "")),
        }
        best_street = None
        best_len = 0
        for street in reference.get("streets", []):
            candidate = _normalize(street)
            if candidate in excluded:
                continue
            if len(candidate) > best_len and _contains_word(text, candidate):
                best_street = street
                best_len = len(candidate)
        if best_street:
            params["street"] = best_street

    return params


def _detect_pending_params(text: str) -> list[str]:
    """Определяет, какие параметры ассистент попросил указать."""
    normalized = _normalize(text)
    if (
        "не хватает" not in normalized
        and "укажите" not in normalized
        and "?" not in text
    ):
        return []

    found: list[str] = []
    for param, label in PARAM_LABELS.items():
        if _normalize(label) in normalized:
            found.append(param)

    extra_labels = {
        "этаж": "floor",
        "площад": "area",
        "год": "year_build",
        "улиц": "street",
        "район": "district",
        "округ": "region",
        "материал": "wall_material",
    }
    for label, param in extra_labels.items():
        if label in normalized and param not in found:
            found.append(param)

    return found


def _parse_bare_value(message: str, pending: list[str],
                      params: dict[str, Any]) -> dict[str, Any]:
    """Разбирает короткий ответ пользователя на уточняющий вопрос."""
    text = message.strip()
    normalized = _normalize(text)
    if not normalized:
        return {}

    extracted = _extract_parameters(text)
    if extracted:
        return extracted

    # Улица вводится свободным текстом: ответ «Первомайская» без слова «улица».
    if "street" in pending and len(text) <= 60:
        words = text.split()
        if 1 <= len(words) <= 4 and not any(char.isdigit() for char in text):
            return {"street": _sentence_start(text)}

    m = re.fullmatch(r"(\d{1,2})\s*(?:лет|год(?:а|ов)?|г\.?)", normalized)
    if m:
        value = int(m.group(1))
        if 1 <= value <= 20:
            return {"n_years": value}

    m = re.fullmatch(r"(\d{1,4}(?:[.,]\d+)?)", normalized)
    if not m:
        return {}

    value = float(m.group(1).replace(",", "."))
    is_int = value.is_integer()
    ival = int(value) if is_int else None

    if is_int and 1800 <= ival <= 2100:
        return {"year_build": ival}

    numeric_pending = [
        param for param in pending if param in ("year_build", "floor", "area")
    ]
    if len(numeric_pending) == 1:
        param = numeric_pending[0]
        if param == "floor" and is_int and ival >= 1:
            return {"floor": ival}
        if param == "area" and value > 0:
            return {"area": value}
        if param == "year_build" and is_int:
            return {"year_build": ival}

    if is_int and 1 <= ival <= 30 and "floor" in pending:
        return {"floor": ival}
    if 1 <= value <= 300 and "area" in pending:
        return {"area": value}

    return {}


def _collect_parameters(message: str, history: list[dict]) -> tuple[dict[str, Any],
                                                                     dict[str, Any]]:
    """Собирает параметры из истории и текущего сообщения.

    Возвращает все известные параметры и то, что удалось распознать
    именно в текущем сообщении.
    """
    params: dict[str, Any] = {}
    pending: list[str] = []

    for item in history:
        role = item.get("role")
        content = item.get("content", "")

        if role == "user":
            extracted = _extract_parameters(content)
            if not extracted:
                extracted = _parse_bare_value(content, pending, params)
            params.update(extracted)
            pending = []
        elif role == "assistant":
            pending = _detect_pending_params(content)

    current = _extract_parameters(message)
    if not current:
        current = _parse_bare_value(message, pending, params)
    params.update(current)

    if "n_years" not in params:
        params["n_years"] = 5
        params["_n_years_default"] = True

    return params, current


def _missing_required(params: dict[str, Any]) -> list[str]:
    """Возвращает список реально недостающих обязательных параметров."""
    return [param for param in REQUIRED_PARAMS if param not in params]


def _pending_params_from_history(history: list[dict]) -> list[str]:
    """Смотрит, что ассистент спросил в последнем сообщении."""
    for item in reversed(history):
        if item.get("role") == "assistant":
            return _detect_pending_params(item.get("content", ""))
    return []


def _is_forecast_context(message: str, history: list[dict],
                         params: dict[str, Any],
                         current: dict[str, Any]) -> bool:
    """Понимает, относится ли сообщение к сценарию прогноза."""
    text = _normalize(message)
    if any(keyword in text for keyword in FORECAST_KEYWORDS):
        return True
    if _pending_params_from_history(history) and current:
        return True
    if not _missing_required(params) and len(current) >= 3:
        return True
    return False


def _param_label(param: str) -> str:
    """Название параметра с примером значения."""
    label = PARAM_LABELS[param]
    hint = PARAM_HINTS.get(param)
    return f"{label} ({hint})" if hint else label


def _sentence_start(text: str) -> str:
    """Делает заглавной только первую букву, не меняя остальной текст."""
    return text[:1].upper() + text[1:]


def _missing_parameters_message(missing: list[str]) -> str:
    """Формирует просьбу указать только недостающие параметры."""
    labels = [_param_label(param) for param in missing]

    if len(labels) == 1:
        return (
            "Для расчёта не хватает одного параметра:\n"
            f"1. {_sentence_start(labels[0])}.\n\n"
            "Укажите его, пожалуйста."
        )

    lines = ["Для расчёта не хватает следующих параметров:"]
    for index, label in enumerate(labels, 1):
        lines.append(f"{index}. {_sentence_start(label)}.")
    lines.append("")
    lines.append("Укажите их, пожалуйста.")
    return "\n".join(lines)


def _format_forecast_confirmation(params: dict[str, Any]) -> str:
    """Готовит подтверждение параметров и команду расчёта для формы."""
    n_years = int(params.get("n_years", 5))
    default_note = " (по умолчанию)" if params.get("_n_years_default") else ""

    payload = {
        "region": params["region"],
        "district": params["district"],
        "street": params["street"],
        "wall_material": params["wall_material"],
        "year_build": int(params["year_build"]),
        "floor": int(params["floor"]),
        "area": float(params["area"]),
        "n_years": n_years,
    }

    lines = [
        "Параметры приняты:",
        f"• Округ: {payload['region']}",
        f"• Район: {payload['district']}",
        f"• Улица: {payload['street']}",
        f"• Материал стен: {payload['wall_material']}",
        f"• Год постройки: {payload['year_build']}",
        f"• Этаж: {payload['floor']}",
        f"• Площадь: {payload['area']:g} м²",
        f"• Горизонт прогноза: {n_years} лет{default_note}",
        "",
        "[[CALCULATE_JSON]]"
        + json.dumps(payload, ensure_ascii=False)
        + "[[/CALCULATE_JSON]]",
    ]

    return "\n".join(lines)


def _build_parameter_hint(params: dict[str, Any]) -> str:
    """Возвращает подсказку для модели по уже собранным параметрам."""
    parts = []
    for key, value in params.items():
        if key.startswith("_"):
            continue
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        parts.append(f"{key}={value}")

    if not parts:
        return ""

    lines = [
        "Примечание системы: в сообщении пользователя и истории диалога "
        "распознаны параметры (используй их, не переспрашивай): "
        + ", ".join(parts)
        + "."
    ]

    if params.get("_n_years_default"):
        lines.append(
            "Горизонт прогноза не указан — используй n_years=5 по умолчанию "
            "и никогда не спрашивай его."
        )

    return "\n".join(lines)


def _extract_text(content: Any) -> str:
    """Извлекает текст из строкового или блочного ответа модели."""
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        parts = []

        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    value = block.get("text", "")
                    if isinstance(value, str):
                        parts.append(value)
            else:
                value = getattr(block, "text", None)
                if isinstance(value, str):
                    parts.append(value)

        text = "\n".join(part for part in parts if part).strip()
    else:
        text = ""

    # Убираем служебный блок размышлений, если модель вернула его
    # вместе с пользовательским ответом.
    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()

    return text


def chat(message: str, history: list[dict] | None = None) -> str:
    """Обрабатывает сообщение и необязательную историю диалога."""
    message = message.strip()

    if not message:
        raise ValueError("Сообщение не должно быть пустым.")

    if len(message) > 4000:
        raise ValueError("Сообщение слишком длинное.")

    messages = []

    # Принимаем только обычные сообщения user/assistant.
    # Ответы инструментов и системные инструкции клиент передавать не может.
    for item in (history or [])[-20:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str) or not content.strip():
            continue

        messages.append({
            "role": role,
            "content": content[:4000],
        })

    # Детерминированно собираем параметры из истории и текущего сообщения.
    # Это гарантирует, что n_years по умолчанию равен 5, а недостающие
    # параметры перечисляются без участия модели.
    params, current = _collect_parameters(message, messages)
    missing = _missing_required(params)

    if _is_forecast_context(message, messages, params, current):
        if missing:
            return _missing_parameters_message(missing)
        return _format_forecast_confirmation(params)

    # Для общих вопросов модель получает уже распознанные параметры,
    # чтобы не переспрашивать их.
    hint = _build_parameter_hint(params)
    if hint:
        message = f"{message}\n\n{hint}"

    messages.append({
        "role": "user",
        "content": message,
    })

    result = get_agent().invoke(
        {"messages": messages},
        config={"recursion_limit": 8},
    )


    result_messages = result.get("messages", [])

    # Ищем последнее сообщение ассистента с непустым текстом.
    for item in reversed(result_messages):
        if getattr(item, "type", "") != "ai":
            continue

        text = _extract_text(getattr(item, "content", ""))

        if text:
            return text
        
    print("\n========== ОТЛАДКА LANGCHAIN ==========")
    print("Тип результата:", type(result))
    print("Результат:", repr(result))
    print("=======================================\n")
    
    raise RuntimeError(
        "Агент не вернул текстовый ответ. "
        "Проверьте логи Flask и совместимость версий LangChain и Ollama."
    )
