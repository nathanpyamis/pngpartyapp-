from django.urls import path

from . import views

urlpatterns = [
    path("", views.app_shell, name="agent_app"),
    path("sw.js", views.service_worker, name="agent_sw"),
    path("manifest.webmanifest", views.manifest, name="agent_manifest"),
]
