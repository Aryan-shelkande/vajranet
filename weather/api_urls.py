from django.urls import path

from weather import api

urlpatterns = [
    path(
        "weather/current/", api.CurrentWeatherAPI.as_view(), name="api-weather-current"
    ),
    path("weather/forecast/", api.ForecastAPI.as_view(), name="api-weather-forecast"),
    path("weather/hourly/", api.HourlyForecastAPI.as_view(), name="api-weather-hourly"),
    path("weather/rainfall/", api.RainfallAPI.as_view(), name="api-rainfall"),
    path("weather/map/", api.MapOverviewAPI.as_view(), name="api-weather-map"),
    path("lightning/recent/", api.LightningRecentAPI.as_view(), name="api-lightning"),
    path("radar/", api.RadarAPI.as_view(), name="api-radar"),
    path("alerts/", api.AlertsAPI.as_view(), name="api-alerts"),
    path("nowcasting/", api.NowcastingAPI.as_view(), name="api-nowcasting"),
    path(
        "locations/search/",
        api.LocationSearchAPI.as_view(),
        name="api-locations-search",
    ),
    path(
        "locations/featured/",
        api.FeaturedLocationsAPI.as_view(),
        name="api-locations-featured",
    ),
    path("data-sources/", api.DataSourcesAPI.as_view(), name="api-data-sources"),
    path("assistant/", api.AIAssistantAPI.as_view(), name="api-assistant"),
]
