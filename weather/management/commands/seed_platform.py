"""Seed featured cities, data sources, hazards, and safety content."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from disasters.models import HazardType
from safety.models import EmergencyKitItem, SafetyGuideline
from weather.models import DataSource
from weather.services.weather import LocationService

DATA_SOURCES = [
    {
        "slug": "open-meteo",
        "name": "Open-Meteo",
        "data_type": "Current weather, hourly/daily forecast, CAPE",
        "update_frequency": "Model-dependent (often hourly–3-hourly)",
        "coverage": "Global including India",
        "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)",
        "homepage_url": "https://open-meteo.com/",
        "docs_url": "https://open-meteo.com/en/docs",
        "status": DataSource.Status.AVAILABLE,
        "notes": "Development / evaluation data source. Free non-commercial tier ≈10k calls/day. Not an operational MoES/IMD production feed. Commercial use requires Open-Meteo paid/customer API or self-host.",
    },
    {
        "slug": "open-meteo-geocoding",
        "name": "Open-Meteo Geocoding",
        "data_type": "City / place search",
        "update_frequency": "On demand",
        "coverage": "Global (filtered to IN)",
        "attribution": "Open-Meteo Geocoding API",
        "homepage_url": "https://open-meteo.com/en/docs/geocoding-api",
        "docs_url": "https://open-meteo.com/en/docs/geocoding-api",
        "status": DataSource.Status.AVAILABLE,
        "notes": "Development / evaluation geocoding. India-focused search in VajraNet.",
    },
    {
        "slug": "openfreemap",
        "name": "OpenFreeMap",
        "data_type": "Vector basemap styles (Liberty)",
        "update_frequency": "CDN-hosted styles/tiles",
        "coverage": "Global",
        "attribution": "OpenFreeMap © OpenMapTiles Data from OpenStreetMap",
        "homepage_url": "https://openfreemap.org/",
        "docs_url": "https://openfreemap.org/quick_start/",
        "status": DataSource.Status.AVAILABLE,
        "notes": "Public map styles without an API key. Attribution required. Prefer over OSM volunteer raster tile servers for app demos.",
    },
    {
        "slug": "imd",
        "name": "India Meteorological Department (IMD)",
        "data_type": "Official Indian forecasts, nowcasts, warnings",
        "update_frequency": "Official product cadence",
        "coverage": "India",
        "attribution": "India Meteorological Department",
        "homepage_url": "https://mausam.imd.gov.in/",
        "docs_url": "https://api.imd.gov.in/public/api_reference.html",
        "status": DataSource.Status.REQUIRES_KEY,
        "notes": "Public API portal exists but unauthenticated calls return HTTP 401. Contact IMD for access.",
    },
    {
        "slug": "rainviewer",
        "name": "RainViewer",
        "data_type": "Weather radar tiles",
        "update_frequency": "~5 minutes",
        "coverage": "Global radar mosaic",
        "attribution": "Weather data by RainViewer",
        "homepage_url": "https://www.rainviewer.com/api.html",
        "docs_url": "https://www.rainviewer.com/api.html",
        "status": DataSource.Status.AVAILABLE,
        "notes": "Free for personal/educational/small-community use per current RainViewer terms. Not an official IMD radar product. Attribution required.",
    },
    {
        "slug": "usgs",
        "name": "USGS Earthquake Catalog",
        "data_type": "Earthquake events",
        "update_frequency": "Near real-time",
        "coverage": "Global (queried for India bbox)",
        "attribution": "U.S. Geological Survey",
        "homepage_url": "https://earthquake.usgs.gov/",
        "docs_url": "https://earthquake.usgs.gov/fdsnws/event/1/",
        "status": DataSource.Status.AVAILABLE,
        "notes": "Observed earthquake catalog. Not earthquake prediction.",
    },
    {
        "slug": "nasa-firms",
        "name": "NASA FIRMS",
        "data_type": "Active fire / thermal hotspots",
        "update_frequency": "Near real-time satellite overpasses",
        "coverage": "Global",
        "attribution": "NASA FIRMS / LANCE",
        "homepage_url": "https://firms.modaps.eosdis.nasa.gov/",
        "docs_url": "https://firms.modaps.eosdis.nasa.gov/api/",
        "status": DataSource.Status.REQUIRES_KEY,
        "notes": "Free MAP_KEY required via email signup. Optional; not shown as live without a key.",
    },
    {
        "slug": "blitzortung",
        "name": "Blitzortung / LightningMaps",
        "data_type": "Lightning strikes",
        "update_frequency": "Seconds–minutes",
        "coverage": "Network-dependent",
        "attribution": "Blitzortung.org participants",
        "homepage_url": "https://www.blitzortung.org/",
        "docs_url": "https://www.limaps.org/live-data.html",
        "status": DataSource.Status.UNAVAILABLE,
        "notes": "No suitable free redistributable live lightning feed is configured. Raw feeds require participant credentials.",
    },
    {
        "slug": "ndma-sachet",
        "name": "NDMA SACHET",
        "data_type": "Official CAP disaster alerts",
        "update_frequency": "Event-driven",
        "coverage": "India",
        "attribution": "National Disaster Management Authority",
        "homepage_url": "https://sachet.ndma.gov.in/",
        "docs_url": "https://sachet.ndma.gov.in/",
        "status": DataSource.Status.PLANNED,
        "notes": "Official alerts — integration pending until a legitimate machine-readable feed is verified. Do not scrape the HTML UI.",
    },
]

HAZARDS = [
    ("thunderstorm", "Thunderstorm", "weather", True),
    ("lightning", "Lightning", "weather", True),
    ("heavy-rainfall", "Heavy rainfall", "weather", True),
    ("heatwave", "Heat wave", "weather", True),
    ("coldwave", "Cold wave", "weather", True),
    ("cyclone", "Cyclone", "weather", False),
    ("flood", "Flood", "hydrological", False),
    ("earthquake", "Earthquake", "geophysical", False),
    ("landslide", "Landslide", "geological", False),
    ("wildfire", "Wildfire", "environmental", False),
    ("air-quality", "Air quality hazard", "environmental", False),
    ("drought", "Drought", "climate", False),
]

GUIDELINES = [
    {
        "slug": "lightning",
        "hazard_name": "Lightning",
        "title": "Lightning safety",
        "summary": "Lightning can strike ahead of or after a storm. Getting indoors early saves lives.",
        "instructions": [
            "Move indoors or into a hard-top vehicle",
            "Avoid isolated trees and open fields",
            "Stay away from metal structures and tall poles",
            "Stay away from water and wet ground when possible",
            "Follow official IMD/NDMA alerts",
        ],
        "official_sources": [
            {"name": "NDMA", "url": "https://ndma.gov.in/"},
            {"name": "IMD", "url": "https://mausam.imd.gov.in/"},
        ],
        "display_order": 1,
    },
    {
        "slug": "thunderstorm",
        "hazard_name": "Thunderstorm",
        "title": "Thunderstorm safety",
        "summary": "Strong winds, lightning, and sudden rain can develop quickly.",
        "instructions": [
            "Stay indoors during severe activity",
            "Secure loose outdoor objects",
            "Avoid windows during intense storms",
            "Avoid unnecessary travel",
        ],
        "official_sources": [{"name": "IMD", "url": "https://mausam.imd.gov.in/"}],
        "display_order": 2,
    },
    {
        "slug": "hailstorm",
        "hazard_name": "Hailstorm",
        "title": "Hailstorm safety",
        "summary": "Hail can damage vehicles, windows, and injure people outdoors.",
        "instructions": [
            "Stay indoors",
            "Protect windows where practical",
            "Avoid driving if conditions are severe",
            "Protect vehicles under cover when safe to do so",
        ],
        "official_sources": [],
        "display_order": 3,
    },
    {
        "slug": "flood",
        "hazard_name": "Flood",
        "title": "Flood safety",
        "summary": "Moving water is dangerous even when it looks shallow.",
        "instructions": [
            "Avoid flooded roads",
            "Move to higher ground when advised",
            "Do not walk or drive through moving water",
            "Follow local authority instructions",
        ],
        "official_sources": [{"name": "NDMA", "url": "https://ndma.gov.in/"}],
        "display_order": 4,
    },
    {
        "slug": "cyclone",
        "hazard_name": "Cyclone",
        "title": "Cyclone safety",
        "summary": "Cyclones bring destructive winds, storm surge, and heavy rain.",
        "instructions": [
            "Follow evacuation instructions",
            "Keep emergency supplies ready",
            "Charge communication devices",
            "Stay indoors during dangerous conditions",
        ],
        "official_sources": [
            {"name": "IMD Cyclone", "url": "https://mausam.imd.gov.in/"},
            {"name": "NDMA", "url": "https://ndma.gov.in/"},
        ],
        "display_order": 5,
    },
    {
        "slug": "earthquake",
        "hazard_name": "Earthquake",
        "title": "Earthquake safety — Drop, Cover, Hold On",
        "summary": "Protect yourself during shaking, then check for hazards.",
        "instructions": [
            "Drop to your hands and knees",
            "Cover your head and neck under sturdy furniture if possible",
            "Hold On until shaking stops",
            "After shaking, check for injuries and gas/electrical hazards",
            "Prepare an emergency kit in advance",
        ],
        "official_sources": [{"name": "NDMA", "url": "https://ndma.gov.in/"}],
        "display_order": 6,
    },
    {
        "slug": "heatwave",
        "hazard_name": "Heatwave",
        "title": "Heatwave safety",
        "summary": "Extreme heat is especially dangerous for children, elders, and outdoor workers.",
        "instructions": [
            "Stay hydrated",
            "Avoid peak afternoon heat",
            "Wear lightweight clothing",
            "Monitor vulnerable individuals",
        ],
        "official_sources": [{"name": "NDMA", "url": "https://ndma.gov.in/"}],
        "display_order": 7,
    },
    {
        "slug": "wildfire",
        "hazard_name": "Wildfire",
        "title": "Wildfire / smoke safety",
        "summary": "Stay clear of fire zones and protect lungs from smoke.",
        "instructions": [
            "Avoid affected areas",
            "Follow evacuation instructions",
            "Protect breathing from smoke",
            "Keep emergency communication available",
        ],
        "official_sources": [],
        "display_order": 8,
    },
]

KIT = [
    ("water", "Water", "At least 3 litres per person per day", "droplet", 1),
    ("first-aid", "First aid", "Bandages, antiseptic, basic supplies", "plus", 2),
    ("flashlight", "Flashlight", "Battery or crank flashlight", "light", 3),
    ("batteries", "Batteries", "Spare batteries for lights and radio", "battery", 4),
    ("power-bank", "Power bank", "Charged portable battery", "bolt", 5),
    ("radio", "Radio", "Battery/hand-crank radio for alerts", "radio", 6),
    ("whistle", "Whistle", "Signal for help", "whistle", 7),
    ("food", "Food", "Non-perishable ready-to-eat food", "food", 8),
    (
        "documents",
        "Important documents",
        "IDs, insurance, medical records (waterproof)",
        "docs",
        9,
    ),
    ("medicines", "Medicines", "Prescriptions and basic OTC meds", "meds", 10),
    ("masks", "Masks", "Dust/smoke protection", "mask", 11),
    ("tools", "Basic tools", "Multi-tool, tape, lighter", "tools", 12),
]


class Command(BaseCommand):
    help = "Seed VajraNet reference data"

    def handle(self, *args, **options):
        created_cities = LocationService().ensure_featured()
        for item in DATA_SOURCES:
            DataSource.objects.update_or_create(slug=item["slug"], defaults=item)
        for slug, name, category, phase1 in HAZARDS:
            HazardType.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "category": category,
                    "phase1_focus": phase1,
                    "is_active": True,
                },
            )
        for g in GUIDELINES:
            SafetyGuideline.objects.update_or_create(slug=g["slug"], defaults=g)
        for slug, name, desc, icon, order in KIT:
            EmergencyKitItem.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "description": desc,
                    "icon": icon,
                    "display_order": order,
                    "is_essential": True,
                },
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded platform data (featured cities created/ensured: {created_cities})"
            )
        )
