from django.urls import path

from safety.api_views import SafetyAPI

urlpatterns = [
    path("safety/", SafetyAPI.as_view(), name="api-safety"),
]
