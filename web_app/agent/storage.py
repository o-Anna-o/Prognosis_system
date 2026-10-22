
# web_app/agent/storage.py

import json
import os
from urllib.request import Request, urlopen
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from agent.anonymizer import anonymize


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://127.0.0.1:11434",
).rstrip("/")
OLLAMA_EMBED_MODEL = os.getenv(
    "OLLAMA_EMBED_MODEL",
    "nomic-embed-text",
)
CONVERSATION_ID = UUID(
    os.getenv(
        "AGENT_CONVERSATION_ID",
        "11111111-1111-4111-8111-111111111111",
    )
)


def _connect():
    if not DATABASE_URL:
        raise RuntimeError("Не задан DATABASE_URL в .env")

    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        connect_timeout=5,
    )


def init_storage():
    """Создаёт диалог, если он ещё не создан."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversations (id)
            VALUES (%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (CONVERSATION_ID,),
        )


def get_recent_history(limit=20):
    """Возвращает последние сообщения в хронологическом порядке."""
    limit = max(1, min(int(limit), 100))

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (CONVERSATION_ID, limit),
        ).fetchall()

    rows.reverse()
    return [
        {"role": row["role"], "content": row["content"]}
        for row in rows
    ]


def _create_embedding(text):
    """Строит эмбеддинг только для предварительно очищенного текста."""
    payload = json.dumps({
        "model": OLLAMA_EMBED_MODEL,
        "input": text,
    }).encode("utf-8")

    request = Request(
        f"{OLLAMA_BASE_URL}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))

    embeddings = result.get("embeddings", [])
    if not embeddings or not embeddings[0]:
        raise RuntimeError("Ollama не вернула эмбеддинг")

    embedding = embeddings[0]

    if len(embedding) != 768:
        raise ValueError(
            f"Ожидался вектор из 768 элементов, получено: {len(embedding)}"
        )

    return embedding


def save_turn(user_text, assistant_text):
    """
    Сохраняет очищенные сообщения.
    Персональные данные удаляются до записи в БД и до эмбеддинга.
    """
    clean_user = anonymize(user_text).strip()
    clean_assistant = anonymize(assistant_text).strip()

    # Не сохраняем пустые сообщения.
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO conversations (id)
            VALUES (%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (CONVERSATION_ID,),
        )

        user_row = None
        assistant_row = None

        if clean_user:
            user_row = conn.execute(
                """
                INSERT INTO messages
                    (conversation_id, role, content)
                VALUES (%s, 'user', %s)
                RETURNING id
                """,
                (CONVERSATION_ID, clean_user),
            ).fetchone()

        if clean_assistant:
            assistant_row = conn.execute(
                """
                INSERT INTO messages
                    (conversation_id, role, content)
                VALUES (%s, 'assistant', %s)
                RETURNING id
                """,
                (CONVERSATION_ID, clean_assistant),
            ).fetchone()

        conn.execute(
            """
            UPDATE conversations
            SET updated_at = NOW()
            WHERE id = %s
            """,
            (CONVERSATION_ID,),
        )

    # История уже сохранена. Если Ollama временно недоступна,
    # это не должно отменять ответ пользователю.
    combined = "\n".join(
        part for part in (
            f"Пользователь: {clean_user}" if clean_user else "",
            f"Ассистент: {clean_assistant}" if clean_assistant else "",
        )
        if part
    ).strip()

    if not combined:
        return

    try:
        embedding = _create_embedding(combined)
        vector_value = "[" + ",".join(map(str, embedding)) + "]"

        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_chunks
                    (conversation_id, message_id, content, embedding)
                VALUES (%s, %s, %s, %s::vector)
                """,
                (
                    CONVERSATION_ID,
                    assistant_row["id"] if assistant_row else (
                        user_row["id"] if user_row else None
                    ),
                    combined,
                    vector_value,
                ),
            )
    except Exception:
        # Не выводим тексты сообщений и персональные данные в логи.
        # Ошибку векторизации можно диагностировать отдельно.
        return


def search_memory(query, limit=5):
    """Находит похожие фрагменты в памяти текущего диалога."""
    clean_query = anonymize(query).strip()
    if not clean_query:
        return []

    limit = max(1, min(int(limit), 20))

    try:
        embedding = _create_embedding(clean_query)
    except Exception:
        return []

    vector_value = "[" + ",".join(map(str, embedding)) + "]"

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT content,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM memory_chunks
            WHERE conversation_id = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (
                vector_value,
                CONVERSATION_ID,
                vector_value,
                limit,
            ),
        ).fetchall()

    return [
        {
            "content": row["content"],
            "similarity": float(row["similarity"]),
        }
        for row in rows
    ]
