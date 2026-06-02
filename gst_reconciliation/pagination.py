from __future__ import annotations

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class GstReconciliationPagination(PageNumberPagination):
    page_query_param = "page"
    page_size_query_param = "pagesize"
    page_size = 25
    max_page_size = 200

    def get_paginated_response(self, data, *, meta_echo=None):
        return Response(
            {
                "meta": {
                    "count": self.page.paginator.count,
                    "page": self.page.number,
                    "pages": self.page.paginator.num_pages,
                    "page_size": self.get_page_size(self.request),
                    **(meta_echo or {}),
                },
                "rows": data,
            }
        )
