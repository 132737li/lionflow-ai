"""
Helper de pagination SQLAlchemy → dict JSON.
"""
from flask import request


def paginate_query(query, default_per_page: int = 20, max_per_page: int = 100):
    page = request.args.get("page", 1, type=int)
    per_page = min(
        request.args.get("per_page", default_per_page, type=int),
        max_per_page,
    )
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "items": pagination.items,
        "meta": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "has_prev": pagination.has_prev,
            "has_next": pagination.has_next,
            "prev_num": pagination.prev_num,
            "next_num": pagination.next_num,
        },
    }