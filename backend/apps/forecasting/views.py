from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import services

logger = logging.getLogger(__name__)


@api_view(["GET"])
def health(request):
    return Response({"ok": True})


@api_view(["GET"])
def model_status(request):
    return Response(services.get_status())


@api_view(["GET"])
def reference(request):
    try:
        return Response(services.get_reference())
    except Exception:
        return Response({"error": "Справочные данные ещё не загружены."}, status=503)


@api_view(["GET"])
def eda(request):
    try:
        return Response(services.get_eda_charts())
    except Exception:
        return Response({"error": "Не удалось подготовить аналитические данные."}, status=503)


@api_view(["POST"])
def predict(request):
    try:
        return Response(services.build_prediction(request.data))
    except services.PayloadValidationError as exc:
        return Response({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Prediction request failed")
        return Response({"error": f"Ошибка прогноза: {exc}"}, status=500)


@api_view(["POST"])
def predict_batch(request):
    data = request.data
    if not isinstance(data, list) or not data:
        return Response({"error": "Ожидается непустой JSON-массив квартир."}, status=400)

    validated: list[tuple[str, dict]] = []
    seen_ids: set[str] = set()
    horizon: int | None = None
    try:
        for index, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Квартира {index}, поле «объект»: ожидается JSON-объект.")
            client_id = item.get("client_id")
            if not isinstance(client_id, str) or not client_id.strip():
                raise ValueError(f"Квартира {index}, поле «client_id»: требуется уникальный идентификатор.")
            if client_id in seen_ids:
                raise ValueError(f"Квартира {index}, поле «client_id»: идентификатор повторяется.")
            seen_ids.add(client_id)
            apartment = services.validate_payload(item)
            if horizon is None:
                horizon = apartment["n_years"]
            elif apartment["n_years"] != horizon:
                raise ValueError(f"Квартира {index}, поле «n_years»: горизонт должен совпадать у всех квартир.")
            validated.append((client_id, item))
    except services.PayloadValidationError as exc:
        return Response({"error": str(exc)}, status=400)

    try:
        results = [
            {"client_id": client_id, "prediction": services.build_prediction(item, include_exact=True)}
            for client_id, item in validated
        ]
    except Exception as exc:
        logger.exception("Batch prediction request failed")
        return Response({"error": f"Ошибка прогноза: {exc}"}, status=500)

    return Response({
        "results": results,
        "comparison": {
            "horizon_years": horizon,
            "base_year": results[0]["prediction"]["base_year"],
            "forecasts": [
                {
                    "client_id": item["client_id"],
                    "forecast": item["prediction"]["forecast"],
                    "forecast_exact": item["prediction"]["forecast_exact"],
                }
                for item in results
            ],
        },
    })
