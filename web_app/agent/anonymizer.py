
import re


# Удаляем телефонные номера с кодами стран и регионами.
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[\s().-]*)?"
    r"(?:\(?\d{3,4}\)?[\s().-]*)"
    r"\d{2,3}(?:[\s.-]*\d{2,3}){1,3}(?!\w)"
)

# Электронные адреса.
EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}"
)

# Российский внутренний паспорт: серия и номер.
PASSPORT_RE = re.compile(
    r"(?i)(?:(?:паспорт|серия\s+паспорта)\s*"
    r"(?:№|номер)?\s*[:№]?\s*)"
    r"\d{2}\s?\d{2}[\s-]*\d{6}"
)

# СНИЛС.
SNILS_RE = re.compile(
    r"(?<!\d)\d{3}-\d{3}-\d{3}\s\d{2}(?!\d)"
)

# ИНН физического лица или организации.
INN_RE = re.compile(
    r"(?i)(?:(?:ИНН)\s*[:№]?\s*)"
    r"\d{10}(?:\d{2})?"
)

# Даты рождения, когда они явно подписаны.
BIRTH_DATE_RE = re.compile(
    r"(?i)(?:дата рождения|родился|родилась|д\.?\s*р\.?)"
    r"\s*[:\-]?\s*"
    r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
)

# Имена после явного представления.
INTRODUCED_NAME_RE = re.compile(
    r"(?i)\b(?:меня зовут|мое имя|моё имя|"
    r"фамилия и имя|фио)\s*[:\-]?\s*"
    r"[А-ЯЁ][а-яё-]+"
    r"(?:\s+[А-ЯЁ][а-яё-]+){0,2}"
)


def _luhn_valid(number: str) -> bool:
    """Проверка контрольной суммы номера карты."""
    digits = [int(ch) for ch in number if ch.isdigit()]

    if not 13 <= len(digits) <= 19:
        return False

    checksum = 0
    parity = len(digits) % 2

    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit

    return checksum % 10 == 0


def _remove_card_numbers(text: str) -> str:
    """Удаляет номера карт"""

    # Номера после явного указания банковской карты.
    labeled = re.compile(
        r"(?i)(?:номер карты|карта|банковская карта|"
        r"card number|card)\s*[:№]?\s*"
        r"(?:\d[ -]?){13,19}"
    )

    def remove_labeled(match: re.Match) -> str:
        candidate = re.search(r"(?:\d[ -]?){13,19}", match.group())
        if candidate and _luhn_valid(candidate.group()):
            return ""
        return match.group()

    text = labeled.sub(remove_labeled, text)

    # Не удаляем произвольные последовательности цифр без проверки.
    candidates = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")

    def remove_valid_card(match: re.Match) -> str:
        candidate = match.group()
        return "" if _luhn_valid(candidate) else candidate

    return candidates.sub(remove_valid_card, text)


def anonymize(text: str) -> str:
    """
    Удаляет распознанные персональные данные
    """
    if not isinstance(text, str):
        raise TypeError("Ожидается строка.")

    result = text

    # Сначала более специфичные шаблоны.
    for pattern in (
        PASSPORT_RE,
        SNILS_RE,
        INN_RE,
        BIRTH_DATE_RE,
        INTRODUCED_NAME_RE,
        EMAIL_RE,
        PHONE_RE,
    ):
        result = pattern.sub("", result)

    result = _remove_card_numbers(result)

    # Убираем лишние пробелы, оставшиеся после удаления.
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r" *([,;:]) *", r"\1 ", result)
    result = re.sub(r" {0,}([.!?])", r"\1", result)
    result = re.sub(r"\s{3,}", "\n\n", result)

    return result.strip()
