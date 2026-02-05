from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from reports.serializers_stock_aging import StockAgingRequestSerializer
from reports.services.stock_aging_service import compute_stock_aging

class StockAgingAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = StockAgingRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        p = ser.validated_data

        rows, bucket_labels, totals = compute_stock_aging(p=p)

        # pagination for JSON only
        page = p.get("page", 1)
        size = p.get("page_size", 50)
        start = (page - 1) * size
        end = start + size

        paged = rows[start:end]

        results = []
        for r in paged:
            results.append({
                "product_id": r["product_id"],
                "product_name": r.get("product_name"),
                "location": r.get("location"),
                "closing_qty": str(r["closing_qty"]),
                "buckets": {k: str(v) for k, v in r["buckets"].items()},
            })

        return Response({
            "entity": p["entity"],
            "as_on_date": str(p["as_on_date"]),
            "group_by_location": p.get("group_by_location", True),
            "bucket_labels": bucket_labels,
            "count": len(results),
            "results": results,
            "totals": {
                "closing_qty": str(totals["closing_qty"]),
                "buckets": {k: str(v) for k, v in totals["buckets"].items()},
                "total_rows": len(rows),
            }
        })
