
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

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


def _street_name_variants(street: str) -> set[str]:
    """Return common Russian case forms for street names from the reference."""
    normalized = _normalize(street)
    variants = {normalized}
    words = normalized.split()
    if words:
        last = words[-1]
        last_forms = {last}
        for ending, replacement in (("ская", "ской"), ("цкая", "цкой"), ("ая", "ой"), ("яя", "ей")):
            if last.endswith(ending):
                last_forms.add(last[:-len(ending)] + replacement)
                break
        first_forms = {words[0]}
        if len(words) > 1 and re.fullmatch(r"\d+-я", words[0]):
            first_forms.add(words[0][:-1] + "й")
        for first in first_forms:
            for last_form in last_forms:
                variants.add(" ".join([first, *words[1:-1], last_form]))
    return variants


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


_YEAR_NUMBER_WORDS = {
    "один": 1, "одна": 1, "одно": 1, "одного": 1, "одной": 1,
    "одному": 1, "одну": 1, "одним": 1,
    "два": 2, "две": 2, "двух": 2, "двум": 2, "двумя": 2,
    "три": 3, "трех": 3, "трем": 3, "тремя": 3,
    "четыре": 4, "четырех": 4, "четырем": 4, "четырьмя": 4,
    "пять": 5, "пяти": 5,
    "шесть": 6, "шести": 6,
    "семь": 7, "семи": 7,
    "восемь": 8, "восьми": 8,
    "девять": 9, "девяти": 9,
    "десять": 10, "десяти": 10,
    "одиннадцать": 11, "одиннадцати": 11,
    "двенадцать": 12, "двенадцати": 12,
    "тринадцать": 13, "тринадцати": 13,
    "четырнадцать": 14, "четырнадцати": 14,
    "пятнадцать": 15, "пятнадцати": 15,
    "шестнадцать": 16, "шестнадцати": 16,
    "семнадцать": 17, "семнадцати": 17,
    "восемнадцать": 18, "восемнадцати": 18,
    "девятнадцать": 19, "девятнадцати": 19,
    "двадцать": 20, "двадцати": 20,
}
_YEAR_NUMBER_PATTERN = "|".join(
    re.escape(word)
    for word in sorted(_YEAR_NUMBER_WORDS, key=len, reverse=True)
)
_YEAR_DURATION_RE = re.compile(
    rf"(?<!\w)(?P<number>\d{{1,2}}|{_YEAR_NUMBER_PATTERN})"
    r"\s*-?\s*(?:летн\w*|годичн\w*|лет|год(?:а|ов)?|г\.?)\b"
)
_HORIZON_CONTEXT_RE = re.compile(
    r"(?:"
    r"\bгоризонт(?:а)?(?:\s+прогноз\w*)?(?:\s+(?:на|составит|равен|будет))*"
    r"|\b(?:прогноз\w*|спрогнозир\w*|предскаж\w*)(?:\s+\w+){0,4}"
    r"|\b(?:на|через)\s+(?:(?:ближайш\w*|следующ\w*|предстоящ\w*|"
    r"последующ\w*|будущ\w*|период)\s+){0,3}"
    r")\s*[,;:]?\s*$"
)


def _extract_forecast_horizon(text: str) -> int | None:
    """Извлекает срок прогноза из чисел и числительных в русской фразе."""
    matches = list(_YEAR_DURATION_RE.finditer(text))
    if not matches:
        return None

    contextual = [
        match for match in matches
        if _HORIZON_CONTEXT_RE.search(text[max(0, match.start() - 80):match.start()])
    ]
    if contextual:
        match = contextual[-1]
    elif len(matches) == 1 and text.strip() == matches[0].group(0):
        # Короткий ответ на уточнение, например «пять лет».
        match = matches[0]
    else:
        return None

    raw_value = match.group("number")
    value = int(raw_value) if raw_value.isdigit() else _YEAR_NUMBER_WORDS[raw_value]
    return value if 1 <= value <= 20 else None


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

    # n_years — горизонт прогноза, включая «на 3 года вперёд» и числа словами.
    n_years = _extract_forecast_horizon(text)
    if n_years is not None:
        params["n_years"] = n_years

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
    if not m:
        floor_words = {
            "первом": 1, "первый": 1, "первом этаже": 1,
            "втором": 2, "второй": 2, "третьем": 3, "третий": 3,
            "четвертом": 4, "четвертый": 4, "пятом": 5, "пятый": 5,
            "шестом": 6, "шестой": 6, "седьмом": 7, "седьмой": 7,
            "восьмом": 8, "восьмой": 8, "девятом": 9, "девятый": 9,
            "десятом": 10, "десятый": 10,
        }
        floor_match = re.search(r"\b(первом|первый|втором|второй|третьем|третий|четвертом|четвертый|пятом|пятый|шестом|шестой|седьмом|седьмой|восьмом|восьмой|девятом|девятый|десятом|десятый)\s+этаж", text)
        if floor_match:
            params["floor"] = floor_words[floor_match.group(1)]
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
            r"(?:кв\.?\s*м|м²|м2|м(?!\w)|кв\.?\s*метр\w*|метр\w*|квадрат\w*)",
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
    if not best_district and selected_region:
        all_districts: dict[str, str] = {}
        for districts in region_districts.values():
            for district in districts:
                all_districts[_normalize(district)] = district
        for official, variants in reference.get("district_aliases", {}).items():
            for variant in variants:
                all_districts.setdefault(_normalize(variant), official)
        best_len = 0
        for candidate, district in all_districts.items():
            if len(candidate) > best_len and _matches(text, candidate):
                best_district = district
                best_len = len(candidate)
    if not best_district and selected_region:
        raw_district = re.search(r"\bрайон(?:е|а)?\s+([^,.;]+)", text)
        if raw_district:
            value = raw_district.group(1)
            value = re.split(r"\b(?:улица|ул\.?|проспект|материал|этаж|площадь|дом)\b", value, maxsplit=1)[0]
            value = value.strip(" ,;:-")
            if value:
                params["district"] = value
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
            if len(candidate) > best_len and any(
                _contains_word(text, variant)
                for variant in _street_name_variants(street)
            ):
                best_street = street
                best_len = len(candidate)
        if best_street:
            params["street"] = best_street

    return params


def _extract_apartment_description(text: str) -> dict[str, Any]:
    """Extract apartment fields, including an unlabelled final area value."""
    params = _extract_parameters(text)
    if "area" not in params:
        trailing = re.search(r"[,;]\s*(\d{1,3}(?:[.,]\d+)?)\s*$", text)
        if trailing:
            area = float(trailing.group(1).replace(",", "."))
            if 1 <= area <= 300:
                params["area"] = area
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


def _is_information_question(text: str) -> bool:
    normalized = _normalize(text)
    asks_about_parameters = any(word in normalized for word in ("параметр", "признак", "характеристик"))
    asks_to_explain = any(word in normalized for word in ("объясни", "расскажи", "какие", "что влияет", "как работает"))
    return asks_about_parameters and asks_to_explain


def _answer_existing_comparison(text: str, context: dict[str, Any] | None) -> str | None:
    normalized = _normalize(text)
    asks_for_comparison = any(word in normalized for word in (
        "перспективнее", "сильнее подорож", "выгоднее", "сравни результаты", "больший прирост", "прирост", "абсолютный рост", "рост стоимости", "вырастет сильнее",
        "что будет дороже", "какая подорожает",
    ))
    if not asks_for_comparison or not isinstance(context, dict):
        return None
    apartments = context.get("apartments")
    if not isinstance(apartments, list) or len(apartments) < 2:
        return None
    rows = [
        item for item in apartments
        if isinstance(item, dict)
        and isinstance(item.get("title"), str)
        and isinstance(item.get("growth"), (int, float))
        and isinstance(item.get("startPrice"), (int, float))
        and isinstance(item.get("endPrice"), (int, float))
    ]
    if len(rows) < 2:
        return None
    asks_for_percent = "процент" in normalized or "%" in normalized
    if asks_for_percent:
        best = max(rows, key=lambda item: float(item["growth"]))
        return f"По процентному росту лидирует {best['title']}: {float(best['growth']):.1f}% за выбранный период."
    best = max(rows, key=lambda item: float(item["endPrice"]) - float(item["startPrice"]))
    growth_rub = round((float(best["endPrice"]) - float(best["startPrice"])) * 1_000_000)
    formatted_growth = f"{growth_rub:,}".replace(",", " ")
    return f"По абсолютному приросту стоимости лидирует {best['title']}: прогнозируемое увеличение за выбранный период — {formatted_growth} ₽."



def starts_new_forecast(message: str, history: list[dict]) -> bool:
    """Detect a new forecast request so values from an older apartment cannot carry over."""
    text = _normalize(message)
    reset_markers = (
        "новая квартира",
        "новую квартиру",
        "одну квартиру",
        "другая квартира",
        "другую квартиру",
        "новый прогноз",
        "другой прогноз",
        "следующая квартира",
        "следующий прогноз",
        "очисти параметры",
        "начни заново",
        "с нуля",
    )
    if any(marker in text for marker in reset_markers):
        return True

    if _is_information_question(text):
        return False

    # Multi-apartment conversation state is stored in the assistant's structured
    # history marker; preserve it for recalculation and later corrections.
    if _state_from_history(history):
        return False

    has_forecast_intent = any(keyword in text for keyword in FORECAST_KEYWORDS)
    return has_forecast_intent and not _pending_params_from_history(history)


def _is_forecast_context(message: str, history: list[dict],
                         params: dict[str, Any],
                         current: dict[str, Any]) -> bool:
    """Понимает, относится ли сообщение к сценарию прогноза."""
    text = _normalize(message)
    if _is_information_question(message):
        return False
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


_APARTMENT_ORDINALS = {
    "перв": 0, "втор": 1, "треть": 2, "четверт": 3, "пят": 4,
    "шест": 5, "седьм": 6, "восьм": 7, "девят": 8, "десят": 9,
}
_STATE_MARKER = "[[APARTMENTS_STATE_JSON]]"


def _requested_apartment_count(text: str) -> int:
    normalized = _normalize(text)
    words = {
        "две": 2, "два": 2, "три": 3, "четыре": 4, "пять": 5,
        "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    }
    match = re.search(r"\b(\d{1,2}|две|два|три|четыре|пять|шесть|семь|восемь|девять|десять)\s+(?:квартир\w*|объект\w*|вариант\w*)", normalized)
    count = int(match.group(1)) if match and match.group(1).isdigit() else words.get(match.group(1), 0) if match else 0
    if re.search(r"\b(?:еще|ещё) одна\b", normalized):
        count = max(count, 2)
    if re.search(r"\bодна\b.*\bдругая\b", normalized):
        count = max(count, 2)
    ordinal_forms = re.finditer(
        r"\b(перва\w*|перву\w*|втор\w*|треть\w*|четверт\w*|пятая|пятой|пятую|шестая|шестой|шестую|восьмая|восьмой|восьмую|девятая|девятой|девятую|десятая|десятой|десятую)\b",
        normalized,
    )
    for ordinal in ordinal_forms:
        if re.match(r"\s+этаж", normalized[ordinal.end():]):
            continue
        word = ordinal.group(1)
        index = next((value for prefix, value in _APARTMENT_ORDINALS.items() if word.startswith(prefix)), None)
        if index is not None:
            count = max(count, index + 1)
    return count


def _state_from_history(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in reversed(history):
        if item.get("role") != "assistant":
            continue
        content = item.get("content", "")
        start = content.find(_STATE_MARKER)
        if start < 0:
            continue
        raw = content[start + len(_STATE_MARKER):].split("[[/APARTMENTS_STATE_JSON]]", 1)[0]
        try:
            state = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(state, dict) and isinstance(state.get("apartments"), list):
            return state
    return None


def _split_apartment_descriptions(text: str, expected_count: int) -> list[str]:
    """Split only on object-level cues; conjunctions between fields stay intact."""
    ordinal = re.compile(
        r"\b(перва\w*|перву\w*|втор\w*|другая|другой|треть\w*|четверт\w*|"
        r"пятая|пятой|пятую|шестая|шестой|шестую|восьмая|восьмой|восьмую|"
        r"девятая|девятой|девятую|десятая|десятой|десятую)\b",
        re.I,
    )
    ordinal_matches = list(ordinal.finditer(text))
    if len(ordinal_matches) >= 2:
        starts = [match.start() for match in ordinal_matches]
        return [text[starts[i]:starts[i + 1]].strip(" ,;:.\n") for i in range(len(starts) - 1)] + [text[starts[-1]:].strip(" ,;:.\n")]

    boundaries = [match.start() for match in re.finditer(r";\s*", text)]
    reference = get_reference_data() or _fallback_reference()
    normalized = _normalize(text)

    # A new region after «и» is a strong apartment boundary. This handles
    # listings that repeat the region but omit ordinal labels.
    region_names = set(reference.get("regions", [])) | set(reference.get("region_names", {}).values())
    for region in sorted((str(value) for value in region_names if value), key=len, reverse=True):
        candidate = _normalize(region)
        pattern = re.compile(r"(?<!\w)" + re.escape(candidate) + r"(?!\w)")
        for match in pattern.finditer(normalized):
            prefix = normalized[max(0, match.start() - 16):match.start()]
            if re.search(r"\bи\s*$", prefix):
                boundaries.append(match.start() - (len(prefix) - len(prefix.rstrip())))

    # A street named after «и» or a semicolon begins another object. Search
    # the application reference so numbered names such as 15-я Парковая remain
    # one street token and their number is never treated as an apartment field.
    street_positions: list[int] = []
    for street in sorted(reference.get("streets", []), key=len, reverse=True):
        candidate = _normalize(street)
        for match in re.finditer(r"(?<!\w)" + re.escape(candidate) + r"(?!\w)", normalized):
            if not any(abs(match.start() - pos) < max(3, len(candidate) // 2) for pos in street_positions):
                street_positions.append(match.start())
    street_positions.sort()
    for position in street_positions[1:]:
        prefix = normalized[max(0, position - 16):position]
        if re.search(r"(?:\bи|;)\s*$", prefix) or re.search(r",\s*$", prefix):
            boundaries.append(position)

    # Explicit address introductions after a conjunction are also boundaries,
    # while «площадь 54 м² и этаж 7» does not match this pattern.
    address_after_and = re.compile(
        r"\bи\s+(?=(?:квартир\w*\b|улиц\w*\b|ул\.?\s|проспект\w*\b|"
        r"на\s+(?!(?:первом|втором|третьем|четвертом|пятом|шестом|седьмом|"
        r"восьмом|девятом|десятом)\s+этаж)[а-яё0-9-]+"
        r"(?=[^.;]{0,100}(?:площад\w*|м²|м2|\d{1,3}\s*м\b))))"
    )
    for match in address_after_and.finditer(normalized):
        boundaries.append(match.start())

    boundaries = sorted(set(position for position in boundaries if 0 < position < len(text)))
    if not boundaries:
        return [text]
    boundaries = boundaries[:max(0, expected_count - 1)]
    starts = [0, *boundaries]
    return [text[starts[i]:starts[i + 1]].strip(" ,;:.\n") for i in range(len(starts) - 1)] + [text[starts[-1]:].strip(" ,;:.\n")]


def _multi_apartment_response(message: str, history: list[dict[str, Any]]) -> str | None:
    """Collect ordinal apartment descriptions and return a batch UI command."""
    text = message.strip()
    normalized = _normalize(text)
    state = _state_from_history(history)
    resolved_index: int | None = None
    clarification_values: dict[str, Any] = {}
    pending_field: str | None = None
    pending_assistant = history[-1].get("content", "") if history and history[-1].get("role") == "assistant" else ""
    pending_question = re.search(r"уточните параметры (\d+)-й квартиры:\s*([^\n]+)", _normalize(pending_assistant))
    if state and pending_question:
        pending_index = int(pending_question.group(1)) - 1
        pending_text = pending_question.group(2)
        pending_fields = [key for key, label in PARAM_LABELS.items() if _normalize(label) in pending_text]
        if 0 <= pending_index < len(state["apartments"]) and len(pending_fields) == 1:
            pending_field = pending_fields[0]
            resolved_index = pending_index
            clarification_values = _extract_apartment_description(text)
            if not clarification_values and re.fullmatch(r"\d{1,4}(?:[.,]\d+)?", normalized):
                raw_value = float(normalized.replace(",", "."))
                if pending_field in ("area", "floor", "year_build"):
                    clarification_values[pending_field] = int(raw_value) if raw_value.is_integer() and pending_field != "area" else raw_value
            if pending_field in clarification_values and pending_field == "area" and clarification_values[pending_field] < 25:
                state_json = json.dumps(state, ensure_ascii=False)
                state_tag = f"{_STATE_MARKER}{state_json}[[/APARTMENTS_STATE_JSON]]"
                return "Площадь квартиры не может быть меньше 25 м². Укажите фактическую площадь квартиры.\n" + state_tag
    if state and history and history[-1].get("role") == "assistant" and "к какой квартире относятся" in _normalize(history[-1].get("content", "")):
        answer = normalized.strip(" .")
        if answer.isdigit():
            resolved_index = int(answer) - 1
        else:
            ordinal_answer = re.search(r"\b(перва\w*|втора\w*|треть\w*|четверт\w*|пята\w*|шест\w*|седьм\w*|восьм\w*|девят\w*|десят\w*)\b", answer)
            if ordinal_answer:
                word = ordinal_answer.group(1)
                resolved_index = next((index for prefix, index in _APARTMENT_ORDINALS.items() if word.startswith(prefix)), None)
        previous_user = next((item.get("content", "") for item in reversed(history[:-1]) if item.get("role") == "user"), "")
        if resolved_index is not None and 0 <= resolved_index < len(state["apartments"]):
            clarification_values = _extract_apartment_description(previous_user)
        else:
            resolved_index = None
    requested = _requested_apartment_count(text)
    if requested == 1 and re.search(r"\b(?:первая|первой|первую)\b", normalized):
        requested = 2
    multi_cue = requested > 1 or any(word in normalized for word in (
        "сравни", "сравнить", "обе квартир", "все квартир", "квартир:",
        "посчитай обе", "рассчитай обе", "пересчитай обе",
        "еще одна", "ещё одна", "их стоимость", "несколько квартир",
        "следующих объектов", "вариант покупки", "жилье сильнее", "жильё сильнее",
        "из этих квартир", "какая из квартир", "какой из квартир",
    ))
    if requested < 2 and multi_cue and any(word in normalized for word in ("обе", "квартиры", "вариант покупки", "жилье сильнее", "жильё сильнее", "из этих квартир")):
        requested = 2
    single_apartment_request = bool(re.search(r"\b(?:одну|одна)\s+квартир", normalized))
    if state and single_apartment_request and requested <= 1 and "сравни" not in normalized:
        return None
    has_ordinal_or_parameters = bool(
        _extract_apartment_description(text)
        or re.search(r"\b(?:перва|перву|втор|треть|четверт|пята|пятой|пятую|шестая|шестой|восьм|девят|десят)\w*\b", normalized)
    )
    if state and resolved_index is None and not multi_cue and not has_ordinal_or_parameters:
        return None
    if state and any(word in normalized for word in ("сравни уже", "сравнить уже", "эти квартиры", "перспективнее")) and not _extract_parameters(text):
        return None
    if not state and not multi_cue:
        return None

    operation = "append" if state and any(word in normalized for word in ("добавь", "добавить", "еще квартир", "ещё квартир")) else "replace"
    replace_markers = ("новый набор", "новые квартир", "другие квартир", "следующие объект", "сравни заново", "с нуля")
    new_set = bool(re.search(r"\bсравни(?:ть)?\s+(?:\d{1,2}|две|два|три|четыре|пять|шесть|семь)\s+квартир", normalized))
    active_start = 0
    if state and operation == "append":
        apartments = [dict(item) for item in state["apartments"]]
        active_start = len(apartments)
        apartments.extend({"client_id": str(uuid4())} for _ in range(max(requested, 1)))
    elif state and not new_set and not any(marker in normalized for marker in replace_markers):
        apartments = state["apartments"]
        operation = state.get("operation", "replace")
        active_start = int(state.get("active_start", 0))
    else:
        count = max(requested, 0)
        if count < 2 and state:
            count = len(state.get("apartments", []))
        if count < 2:
            return None
        apartments = [{"client_id": str(uuid4())} for _ in range(count)]

    # Keep prior values when the current turn only supplies a correction.
    apartments = [dict(item) for item in apartments]
    if resolved_index is not None and clarification_values:
        apartments[resolved_index].update(clarification_values)
    for item in apartments:
        item.setdefault("client_id", str(uuid4()))
    count = len(apartments)

    ordinal_pattern = re.compile(r"\b(перва\w*|перву\w*|первой|одна|одной|втор\w*|другая|другой|треть\w*|четверт\w*|пятая|пятой|пятую|шестая|шестой|шестую|восьмая|восьмой|восьмую|девятая|девятой|девятую|десятая|десятой|десятую)\b", re.I)
    matches = list(ordinal_pattern.finditer(text))
    generic_segments = _split_apartment_descriptions(text, count) if count > 1 else [text]
    if matches and len(matches) < count and len(generic_segments) >= count:
        first_word = _normalize(matches[0].group(1))
        if first_word.startswith(("первая", "первую", "первой")):
            matches = []
    if "две последние" in normalized and count >= 2:
        shared = _extract_parameters(text)
        for item in apartments[-2:]:
            item.update(shared)
    if matches:
        prefix = text[:matches[0].start()]
        if any(word in _normalize(prefix) for word in ("обе", "все", "кажд", "у каждой", "у всех")):
            shared = _extract_parameters(prefix)
            for item in apartments:
                for key, value in shared.items():
                    item.setdefault(key, value)
        for position, match in enumerate(matches):
            word = _normalize(match.group(1))
            index = 0 if word.startswith(("одна", "одной")) else 1 if word.startswith(("другая", "другой")) else next((idx for prefix, idx in _APARTMENT_ORDINALS.items() if word.startswith(prefix)), None)
            if index is None:
                continue
            index += active_start
            if index >= count:
                continue
            end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
            segment = text[match.end():end]
            apartments[index].update(_extract_apartment_description(segment))
        tail = text[matches[-1].end():]
        shared_marker = re.search(r"\b(?:обе|оба|все|кажд\w*|у каждой|у всех)\b", _normalize(tail))
        if shared_marker:
            shared = _extract_parameters(tail[shared_marker.start():])
            for item in apartments:
                for key, value in shared.items():
                    item.setdefault(key, value)
    elif len(generic_segments) >= 2:
        for index, segment in enumerate(generic_segments[:count]):
            apartments[index + active_start].update(_extract_apartment_description(segment))
        common_marker = re.search(r"\b(?:обе|оба|все|кажд\w*|у каждой|у всех)\b", _normalize(generic_segments[-1]))
        if common_marker:
            shared = _extract_parameters(generic_segments[-1][common_marker.start():])
            for item in apartments[active_start:]:
                for key, value in shared.items():
                    item.setdefault(key, value)
    elif count == 1:
        apartments[0].update(_extract_parameters(text))
    else:
        # Common attributes are safe to share only when the user says they apply to all.
        common = _extract_apartment_description(text)
        common_words = ("обе", "все", "кажд", "у каждой", "у всех")
        if any(word in normalized for word in common_words):
            for item in apartments:
                item.update(common)
        elif common and state:
            incomplete = [
                index for index, item in enumerate(apartments)
                if any(key not in item for key in REQUIRED_PARAMS)
            ]
            # Descriptions in a multi-apartment dialogue arrive in order unless
            # the user gives an explicit ordinal; attach unlabelled details to
            # the next incomplete apartment.
            if incomplete:
                apartments[incomplete[0]].update(common)
        elif common and not state:
            apartments[0].update(common)

    if count > 1:
        shared_pattern = re.compile(r"\b(?:обе\w*|обо\w*|все|кажд\w*|у каждой|у всех|для обеих|для обоих)\b", re.I)
        if matches:
            shared_segments = [text[:matches[0].start()]]
            shared_segments.extend(
                text[match.end():(matches[index + 1].start() if index + 1 < len(matches) else len(text))]
                for index, match in enumerate(matches)
            )
        elif len(generic_segments) >= 2:
            shared_segments = generic_segments
        else:
            shared_segments = [text]
        for segment in shared_segments:
            marker = shared_pattern.search(segment)
            if marker:
                shared_values = _extract_parameters(segment[marker.start():])
                for item in apartments[active_start:]:
                    for key, value in shared_values.items():
                        item.setdefault(key, value)
    # Shared forecast horizon is valid for every apartment in the current comparison.
    horizon = _extract_parameters(text).get("n_years")
    if horizon is None and state:
        horizon = state.get("n_years", 5)
    horizon = horizon or 5
    for item in apartments:
        item.setdefault("n_years", horizon)

    reference = get_reference_data() or _fallback_reference()
    region_districts = reference.get("region_districts", {})
    for index, item in enumerate(apartments, 1):
        region = item.get("region")
        district = item.get("district")
        if region and district and district not in region_districts.get(region, []):
            item.pop("district", None)
            available = region_districts.get(region, [])
            options = ", ".join(available)
            state_json = json.dumps({"apartments": apartments, "n_years": horizon, "operation": operation, "active_start": active_start}, ensure_ascii=False)
            state_tag = f"{_STATE_MARKER}{state_json}[[/APARTMENTS_STATE_JSON]]"
            return (
                f"Уточните параметры {index}-й квартиры: район. Район «{district}» "
                f"не относится к округу {region}. Доступные районы: {options}.\n" + state_tag
            )

    next_incomplete = next(
        ((index, item) for index, item in enumerate(apartments, 1)
         if any(key not in item for key in REQUIRED_PARAMS)),
        None,
    )
    invalid_area = next(
        ((index, item) for index, item in enumerate(apartments, 1)
         if item.get("area") is not None and float(item["area"]) < 25),
        None,
    )
    if invalid_area:
        index, item = invalid_area
        item.pop("area", None)
        state_json = json.dumps({"apartments": apartments, "n_years": horizon, "operation": operation, "active_start": active_start}, ensure_ascii=False)
        state_tag = f"{_STATE_MARKER}{state_json}[[/APARTMENTS_STATE_JSON]]"
        return f"Уточните параметры {index}-й квартиры: площадь квартиры. Площадь не может быть меньше 25 м². Укажите фактическую площадь.\n" + state_tag
    state_json = json.dumps({"apartments": apartments, "n_years": horizon, "operation": operation, "active_start": active_start}, ensure_ascii=False)
    state_tag = f"{_STATE_MARKER}{state_json}[[/APARTMENTS_STATE_JSON]]"
    if next_incomplete:
        index, item = next_incomplete
        missing = [PARAM_LABELS[key] for key in REQUIRED_PARAMS if key not in item]
        missing_text = ", ".join(missing)
        return f"Уточните параметры {index}-й квартиры: {missing_text}.\n" + state_tag

    selected = apartments[active_start:] if operation == "append" else apartments
    payload = {"intent": "compare_apartments" if len(selected) > 1 or count > 1 else "predict_apartments", "operation": operation, "apartments": selected}
    summary = "Параметры квартир собраны. Запускаю прогноз через модель."
    command = "[[CALCULATE_JSON]]" + json.dumps(payload, ensure_ascii=False) + "[[/CALCULATE_JSON]]"
    return summary + "\n" + command + "\n" + state_tag


def chat(message: str, history: list[dict] | None = None,
         result_context: dict[str, Any] | None = None) -> str:
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

    multi_response = _multi_apartment_response(message, messages)
    if multi_response is not None:
        return multi_response

    comparison_answer = _answer_existing_comparison(message, result_context)
    if comparison_answer is not None:
        return comparison_answer

    if _is_information_question(message):
        return (
            "Для прогноза модель использует административный округ, район, улицу, "
            "материал стен, год постройки, этаж и площадь квартиры. Горизонт "
            "прогноза задаёт, на сколько лет рассчитываются значения."
        )

    # Детерминированно собираем параметры из истории и текущего сообщения.
    # Это гарантирует, что n_years по умолчанию равен 5, а недостающие
    # параметры перечисляются без участия модели.
    params, current = _collect_parameters(message, messages)
    missing = _missing_required(params)

    if _is_forecast_context(message, messages, params, current):
        if missing:
            return _missing_parameters_message(missing)
        if float(params.get("area", 0)) < 25:
            return "Площадь квартиры не может быть меньше 25 м². Укажите фактическую площадь квартиры."
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
        "Проверьте журнал Django и совместимость версий LangChain и Ollama."
    )
