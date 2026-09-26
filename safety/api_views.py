from rest_framework.response import Response
from rest_framework.views import APIView

from safety.models import EmergencyKitItem, SafetyGuideline


class SafetyAPI(APIView):
    def get(self, request):
        guidelines = list(
            SafetyGuideline.objects.filter(is_published=True).values(
                "slug",
                "hazard_name",
                "title",
                "summary",
                "instructions",
                "official_sources",
            )
        )
        kit = list(
            EmergencyKitItem.objects.all().values(
                "slug", "name", "description", "icon", "is_essential"
            )
        )
        return Response({"guidelines": guidelines, "emergency_kit": kit})
