from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.gstr1.services.meta import build_gstr1_report_meta


class Gstr1MetaAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entity_id = request.query_params.get("entity")
        if not entity_id:
            return Response({"detail": "entity is required."}, status=400)
        entityfinid_id = request.query_params.get("entityfinid") or None
        subentity_id = request.query_params.get("subentity") or None
        return Response(
            build_gstr1_report_meta(
                entity_id=int(entity_id),
                entityfinid_id=int(entityfinid_id) if entityfinid_id else None,
                subentity_id=int(subentity_id) if subentity_id else None,
            )
        )
