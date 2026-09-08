from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsPlatformOperator
from .services import PlatformAccessService


class PlatformMeAPIView(APIView):
    permission_classes = (IsAuthenticated, IsPlatformOperator)

    def get(self, request):
        return Response(PlatformAccessService.capability_snapshot(request.user))
