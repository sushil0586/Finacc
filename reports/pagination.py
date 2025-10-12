# reports/pagination.py
from rest_framework.pagination import PageNumberPagination

class SmallPageNumberPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "size"   # allow ?size=50
    max_page_size = 1000
