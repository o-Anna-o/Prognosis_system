
import pandas as pd

KNOWLEDGE = pd.DataFrame(
    [
        {
            "id": 1,
            "category": "instruction",
            "title": "Заполнение формы прогноза",
            "content": (
                "Для прогноза указываются регион, район, улица, "
                "материал стен, год постройки, этаж, площадь "
                "квартиры и срок прогноза."
            ),
        },
        {
            "id": 2,
            "category": "instruction",
            "title": "Проверка данных",
            "content": (
                "Перед расчётом необходимо заполнить обязательные "
                "поля. Год постройки должен быть целым числом не "
                "меньше 1800. Этаж и площадь должны быть больше нуля. "
                "Срок прогноза должен составлять от 1 до 20 лет."
            ),
        },
        {
            "id": 3,
            "category": "error",
            "title": "Ошибка при прогнозировании",
            "content": (
                "Проверьте обязательные поля и формат числовых "
                "значений. Если ошибка сохраняется, обновите страницу "
                "и повторите попытку. Если не работает только чат, "
                "можно воспользоваться обычной формой прогноза."
            ),
        },
        {
            "id": 4,
            "category": "security",
            "title": "Защита данных",
            "content": (
                "Не запрашивайте пароли и другие секретные данные. "
                "Не сохраняйте сведения о квартире и личные данные "
                "пользователя в долговременную память. Не изменяйте "
                "исходные датасеты и параметры обученной модели."
            ),
        },
        {
            "id": 5,
            "category": "instruction",
            "title": "Распознавание значений параметров",
            "content": (
                "Значения могут быть указаны с единицами измерения: "
                "«горизонт прогноза 8 лет» — это n_years = 8; "
                "«площадь 60 м²» — это area = 60; «7-й этаж» — floor = 7; "
                "«1969 года» — year_build = 1969. "
                "Единицы измерения («лет», «м²», «этаж») не делают "
                "параметр неуказанным. Не переспрашивай параметр, "
                "если пользователь уже назвал его значение."
            ),
        },
    ],
    columns=["id", "category", "title", "content"],
)


def search_knowledge(query: str, limit: int = 5) -> list[dict]:
    """Ищет подходящие записи в таблице знаний."""
    query_words = {
        word.lower().strip(".,!?():;\"'")
        for word in query.split()
        if len(word) > 2
    }

    if not query_words:
        return []

    results = []

    for row in KNOWLEDGE.to_dict(orient="records"):
        text = (
            f"{row['category']} "
            f"{row['title']} "
            f"{row['content']}"
        ).lower()

        score = sum(word in text for word in query_words)

        if score > 0:
            results.append((score, row))

    results.sort(key=lambda item: item[0], reverse=True)

    return [
        row
        for _, row in results[:max(1, min(limit, 10))]
    ]


def add_knowledge(
    category: str,
    title: str,
    content: str,
) -> int:
    """Добавляет утверждённую запись в таблицу текущего процесса."""
    global KNOWLEDGE

    next_id = (
        int(KNOWLEDGE["id"].max()) + 1
        if not KNOWLEDGE.empty
        else 1
    )

    new_row = pd.DataFrame(
        [{
            "id": next_id,
            "category": category,
            "title": title,
            "content": content,
        }]
    )

    KNOWLEDGE = pd.concat(
        [KNOWLEDGE, new_row],
        ignore_index=True,
    )

    return next_id
