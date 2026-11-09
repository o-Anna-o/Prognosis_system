from django.urls import path

from . import views


urlpatterns = [
    path("health", views.health, name="health"),
    path("status", views.model_status, name="model-status"),
    path("reference", views.reference, name="reference"),
    path("eda", views.eda, name="eda"),
    path("predict", views.predict, name="predict"),
    path("predict/batch", views.predict_batch, name="predict-batch"),
]
