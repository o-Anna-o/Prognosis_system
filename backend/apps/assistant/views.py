from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.forecasting.services import (
    PayloadValidationError,
    build_prediction,
    get_reference,
)

logger = logging.getLogger(__name__)
WEB_APP_DIR = Path(__file__).resolve().parents[3] / "web_app"
if str(WEB_APP_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_APP_DIR))

from agent.service import chat as agent_chat  # noqa: E402
from agent.storage import get_recent_history, init_storage, save_turn  # noqa: E402
from agent.tools import configure_predictor, configure_reference_provider  # noqa: E402


def _predict_for_agent(payload: dict) -> dict:
    try:
        return build_prediction(payload)
    except PayloadValidationError:
        return {"ok": False, "error": "Проверьте параметры квартиры."}
    except Exception:
        logger.exception("Agent prediction tool failed")
        return {"ok": False, "error": "Прогноз сейчас недоступен."}


configure_predictor(_predict_for_agent)
configure_reference_provider(lambda: get_reference())


@api_view(["POST"])
def chat(request):
    payload = request.data
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, str) or not message.strip():
        return Response({"error": "Введите сообщение"}, status=400)
    message = message.strip()
    if len(message) > 4000:
        return Response({"error": "Сообщение слишком длинное"}, status=400)
    try:
        init_storage()
        history = get_recent_history(limit=20)
        answer = agent_chat(message, history=history)
        save_turn(message, answer)
        return Response({"answer": answer})
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Assistant request failed")
        provider_status = getattr(exc, "status_code", None)
        provider_error = str(getattr(exc, "error", "")).strip()
        if provider_status == 503:
            model_name = os.getenv("OLLAMA_MODEL", "qwen3:8b")
            message = (
                f"Ollama вернула HTTP 503 при обращении к модели {model_name}. "
                "Проверьте, что Ollama запущена, эта модель доступна и ей хватает памяти. "
                "Затем повторите запрос."
            )
            if provider_error:
                message += f" Детали Ollama: {provider_error[:300]}"
            return Response({"error": message, "provider": "ollama"}, status=503)
        return Response({"error": "Не удалось обработать сообщение. Проверьте журнал Django."}, status=503)
