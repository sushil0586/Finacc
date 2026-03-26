from django.http import JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView


class ReportsPingAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return JsonResponse(
            {
                "ok": True,
                "service": "reports",
                "version_marker": "gstr3b_export_routes_active",
            }
        )
