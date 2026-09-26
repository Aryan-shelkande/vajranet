from django.urls import path

from disasters.services import DisasterListAPI, EarthquakeAPI, WildfireAPI

urlpatterns = [
    path("disasters/", DisasterListAPI.as_view(), name="api-disasters"),
    path("disasters/earthquakes/", EarthquakeAPI.as_view(), name="api-earthquakes"),
    path("disasters/wildfires/", WildfireAPI.as_view(), name="api-wildfires"),
]
