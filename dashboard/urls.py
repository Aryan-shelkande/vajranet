from django.urls import path

from dashboard import views

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("nowcasting/", views.NowcastingPage.as_view(), name="nowcasting"),
    path("weather/", views.WeatherPage.as_view(), name="weather"),
    path("radar/", views.RadarPage.as_view(), name="radar"),
    path("lightning/", views.LightningPage.as_view(), name="lightning"),
    path("rainfall/", views.RainfallPage.as_view(), name="rainfall"),
    path("temperature/", views.TemperaturePage.as_view(), name="temperature"),
    path("alerts/", views.AlertsPage.as_view(), name="alerts"),
    path("safety/", views.SafetyPage.as_view(), name="safety"),
    path("data-sources/", views.DataSourcesPage.as_view(), name="data-sources"),
    path("monitoring/", views.MonitoringPage.as_view(), name="monitoring"),
    path("sms/subscribe/", views.SMSSubscribeView.as_view(), name="sms-subscribe"),
    path("ask/", views.AskVajraNetView.as_view(), name="ask-vajranet"),
    path(
        "alerts/unsubscribe/",
        views.SMSUnsubscribeView.as_view(),
        name="sms-unsubscribe",
    ),
    path(
        "alerts/unsubscribe/<str:token>/",
        views.SMSUnsubscribeView.as_view(),
        name="sms-unsubscribe-token",
    ),
]
