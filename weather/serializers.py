"""Serializers for weather domain models."""

from rest_framework import serializers

from weather.models import DataSource, Location, WeatherAlert


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = [
            "id",
            "name",
            "state",
            "district",
            "country_code",
            "latitude",
            "longitude",
            "timezone",
            "population",
            "is_featured",
        ]


class DataSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSource
        fields = [
            "slug",
            "name",
            "data_type",
            "update_frequency",
            "coverage",
            "attribution",
            "homepage_url",
            "docs_url",
            "status",
            "notes",
        ]


class WeatherAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeatherAlert
        fields = [
            "id",
            "hazard_type",
            "title",
            "description",
            "severity",
            "origin",
            "area_name",
            "starts_at",
            "ends_at",
            "source_name",
            "recommended_action",
            "is_active",
        ]
