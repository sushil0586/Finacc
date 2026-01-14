from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from reports.serializers_stock_movement import StockMovementRequestSerializer
from reports.services.stock_movement_service import compute_stock_movement

class StockMovementAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = StockMovementRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        p = ser.validated_data

        data = compute_stock_movement(p=p)

        # pagination for JSON summary
        page = p.get("page", 1)
        size = p.get("page_size", 50)
        start = (page - 1) * size
        end = start + size

        summary = data["summary"]
        resp = {
            "entity": p["entity"],
            "from_date": str(p["from_date"]),
            "to_date": str(p["to_date"]),
            "count": len(summary[start:end]),
            "results": [
                {**r,
                 "opening_qty": str(r["opening_qty"]),
                 "opening_value": str(r["opening_value"]),
                 "in_qty": str(r["in_qty"]),
                 "in_value": str(r["in_value"]),
                 "out_qty": str(r["out_qty"]),
                 "out_value": str(r["out_value"]),
                 "net_qty": str(r["net_qty"]),
                 "closing_qty": str(r["closing_qty"]),
                 "closing_value": str(r["closing_value"]),
                 }
                for r in summary[start:end]
            ],
            "totals": {k: str(v) for k, v in data["totals"].items()}
        }

        if p.get("include_details") and data["details"] is not None:
            resp["details"] = [
                {**d,
                 "qty": str(d["qty"]),
                 "unit_cost": str(d["unit_cost"]),
                 "ext_cost": str(d["ext_cost"]),
                 }
                for d in data["details"]
            ]

        return Response(resp)
