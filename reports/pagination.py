# reports/pagination.py
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class SmallPageNumberPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "size"   # allow ?size=50
    max_page_size = 1000


class SimpleNumberPagination(PageNumberPagination):
    page_query_param = "page"
    page_size_query_param = "pagesize"
    max_page_size = 2000

    def get_paginated_response(self, data, *, totals=None, meta_echo=None):
        return Response({
            "meta": {
                "count": self.page.paginator.count,
                "page": self.page.number,
                "pages": self.page.paginator.num_pages,
                **(meta_echo or {}),
                "totals": totals or {},
            },
            "rows": data,
        })
