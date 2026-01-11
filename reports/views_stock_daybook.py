from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from reports.serializers import StockDayBookRequestSerializer
from reports.services.stock_daybook_service import compute_stock_daybook

class StockDayBookAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = StockDayBookRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        p = serializer.validated_data

        data = compute_stock_daybook(
            entity_id=p["entity"],
            from_date=p["from_date"],
            to_date=p["to_date"],
            product_id=p.get("product"),
            location_id=p.get("location"),
            group_by_location=p.get("group_by_location", True),
            include_details=p.get("include_details", False),
        )

        return Response({
            "entity": p["entity"],
            "from_date": str(p["from_date"]),
            "to_date": str(p["to_date"]),
            "group_by_location": p.get("group_by_location", True),
            "include_details": p.get("include_details", False),
            **data
        })
