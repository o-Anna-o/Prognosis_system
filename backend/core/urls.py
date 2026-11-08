from django.urls import include, path


urlpatterns = [
    path("api/apartments/", include("apps.apartments.urls")),
    path("api/forecasting/", include("apps.forecasting.urls")),
    path("api/comparison/", include("apps.comparison.urls")),
    path("api/assistant/", include("apps.assistant.urls")),
    path("api/reference-data/", include("apps.reference_data.urls")),
]
