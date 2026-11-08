from django.urls import include, path


urlpatterns = [
    path("api/", include("apps.forecasting.urls")),
    path("api/forecasting/", include("apps.forecasting.urls")),
    path("api/assistant/", include("apps.assistant.urls")),
    path("api/agent/", include("apps.assistant.urls")),
]
