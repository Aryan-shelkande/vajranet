"""Weather REST API views."""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from rest_framework.response import Response
from rest_framework.views import APIView

from weather.models import DataSource, Location
from weather.providers.base import ProviderError
from weather.serializers import DataSourceSerializer, LocationSerializer
from weather.services.alert import AlertService
from weather.services.forecast import ForecastService
from weather.services.lightning import LightningService, RadarService
from weather.services.nowcasting import NowcastingService
from weather.services.weather import LocationService, WeatherService


def _parse_location_id(raw: str | None) -> tuple[int | None, Response | None]:
    if not raw:
        return None, None
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, Response({"error": "invalid_location_id"}, status=400)


def _city_params(request):
    return {
        "city": request.query_params.get("city"),
        "location_id": request.query_params.get("location_id"),
    }


class CurrentWeatherAPI(APIView):
    def get(self, request):
        params = _city_params(request)
        location_id, err = _parse_location_id(params["location_id"])
        if err:
            return err
        params["location_id"] = location_id
        if not params["city"] and not params["location_id"]:
            params["city"] = "Pune"
        try:
            data = WeatherService().get_current(**params)
        except ObjectDoesNotExist:
            return Response({"error": "location_not_found"}, status=404)
        except ProviderError as exc:
            return Response(
                {"error": "provider_error", "message": str(exc)}, status=502
            )
        return Response(data)


class ForecastAPI(APIView):
    def get(self, request):
        params = _city_params(request)
        location_id, err = _parse_location_id(params["location_id"])
        if err:
            return err
        params["location_id"] = location_id
        if not params["city"] and not params["location_id"]:
            params["city"] = "Pune"
        try:
            data = ForecastService().get_forecast(**params)
        except ObjectDoesNotExist:
            return Response({"error": "location_not_found"}, status=404)
        except ProviderError as exc:
            return Response(
                {"error": "provider_error", "message": str(exc)}, status=502
            )
        return Response(data)


class HourlyForecastAPI(APIView):
    def get(self, request):
        params = _city_params(request)
        location_id, err = _parse_location_id(params["location_id"])
        if err:
            return err
        params["location_id"] = location_id
        if not params["city"] and not params["location_id"]:
            params["city"] = "Pune"
        try:
            return Response(ForecastService().get_hourly(**params))
        except ObjectDoesNotExist:
            return Response({"error": "location_not_found"}, status=404)
        except ProviderError as exc:
            return Response(
                {"error": "provider_error", "message": str(exc)}, status=502
            )


class LocationSearchAPI(APIView):
    def get(self, request):
        q = request.query_params.get("q", "")
        results = LocationService().search(q)
        return Response({"query": q, "results": results})


class LightningRecentAPI(APIView):
    def get(self, request):
        raw = request.query_params.get("minutes", "60")
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            return Response({"error": "invalid_minutes"}, status=400)
        if minutes < 1 or minutes > 180:
            return Response({"error": "minutes_out_of_range"}, status=400)
        return Response(LightningService().get_recent_india(minutes=minutes))


class RainfallAPI(APIView):
    def get(self, request):
        city = request.query_params.get("city", "Pune")
        try:
            current = WeatherService().get_current(city=city)
            forecast = ForecastService().get_forecast(city=city)
        except ObjectDoesNotExist:
            return Response({"error": "location_not_found"}, status=404)
        except ProviderError as exc:
            return Response(
                {"error": "provider_error", "message": str(exc)}, status=502
            )
        return Response(
            {
                "location": current["location"],
                "current_rainfall_mm": current.get("rainfall_mm"),
                "data_kind": current.get("data_kind"),
                "source": current.get("source"),
                "observed_at": current.get("observed_at"),
                "timezone": current.get("timezone"),
                "hourly": [
                    {
                        "time": h.get("time"),
                        "precipitation_mm": h.get("precipitation_mm"),
                        "precipitation_probability_pct": h.get(
                            "precipitation_probability_pct"
                        ),
                    }
                    for h in (forecast.get("hourly") or [])
                ],
                "daily": [
                    {
                        "time": d.get("time"),
                        "precipitation_mm": d.get("precipitation_mm"),
                        "precipitation_probability_pct": d.get(
                            "precipitation_probability_pct"
                        ),
                    }
                    for d in (forecast.get("daily") or [])
                ],
            }
        )


class AlertsAPI(APIView):
    def get(self, request):
        city = request.query_params.get("city")
        location_id, err = _parse_location_id(request.query_params.get("location_id"))
        if err:
            return err
        try:
            return Response(
                AlertService().get_alerts(city=city, location_id=location_id)
            )
        except ObjectDoesNotExist:
            return Response({"error": "location_not_found"}, status=404)
        except ProviderError as exc:
            return Response(
                {"error": "provider_error", "message": str(exc)}, status=502
            )


class NowcastingAPI(APIView):
    def get(self, request):
        city = request.query_params.get("city", "Pune")
        try:
            return Response(NowcastingService().assess(city=city))
        except ObjectDoesNotExist:
            return Response({"error": "location_not_found"}, status=404)
        except ProviderError as exc:
            return Response(
                {"error": "provider_error", "message": str(exc)}, status=502
            )


class MapOverviewAPI(APIView):
    def get(self, request):
        return Response({"cities": WeatherService().get_map_overview()})


class RadarAPI(APIView):
    def get(self, request):
        return Response(RadarService().get_radar())


class DataSourcesAPI(APIView):
    def get(self, request):
        qs = DataSource.objects.filter(is_active=True)
        return Response(DataSourceSerializer(qs, many=True).data)


class FeaturedLocationsAPI(APIView):
    def get(self, request):
        qs = Location.objects.filter(is_featured=True, country_code="IN")
        return Response(LocationSerializer(qs, many=True).data)


class AIAssistantAPI(APIView):
    """Vajra AI — LLM when configured, otherwise labeled platform guidance."""

    def post(self, request):
        from weather.services.ai_assistant import (
            AIAssistant,
            is_question_safe_length,
            sanitize_ai_context,
        )

        question = request.data.get("question") if hasattr(request, "data") else None
        if not isinstance(question, str):
            question = request.query_params.get("question", "")
        question = (question or "").strip()
        if not question:
            return Response({"error": "missing_question"}, status=400)
        if not is_question_safe_length(question):
            return Response({"error": "invalid_question"}, status=400)

        raw_context = request.data.get("context") if hasattr(request, "data") else None
        context = sanitize_ai_context(
            raw_context if isinstance(raw_context, dict) else {}
        )
        result = AIAssistant().answer(question, context)
        return Response(result)
