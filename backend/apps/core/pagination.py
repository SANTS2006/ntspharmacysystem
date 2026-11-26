from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """25 rows by default; lists that fill drop-downs may ask for up to 200."""
    page_size_query_param = "page_size"
    max_page_size = 200
