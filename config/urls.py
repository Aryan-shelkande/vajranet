"""Root URL configuration for VajraNet."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView


def health(_request):
    return JsonResponse({"status": "ok", "service": "vajranet"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),
    path("", include("dashboard.urls")),
    path("api/", include("weather.api_urls")),
    path("api/", include("disasters.api_urls")),
    path("api/", include("safety.api_urls")),
]

admin.site.site_header = "VajraNet Administration"
admin.site.site_title = "VajraNet Admin"
admin.site.index_title = "India Atmospheric & Disaster Intelligence"
