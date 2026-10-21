
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain_ollama import ChatOllama

from .tools import AGENT_TOOLS


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
        num_predict=512,
    )

    return create_agent(
        model=model,
        tools=AGENT_TOOLS,
        system_prompt=load_system_prompt(),
    )


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

    messages.append({
        "role": "user",
        "content": message,
    })


    messages.append({"role": "user", "content": message})

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
