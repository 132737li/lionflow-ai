"""
Routes pour la recherche globale.
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required

from app.services.search_service import SearchService
from app.utils.decorators import require_business, get_current_business


search_bp = Blueprint("search", __name__, url_prefix="/search")


@search_bp.route("/", methods=["GET"])
@login_required
@require_business
def global_search():
    """Endpoint de recherche globale (AJAX)."""
    query = (request.args.get("q") or "").strip()
    business = get_current_business()

    if not query or len(query) < 2:
        return jsonify(
            success=True,
            query=query,
            results={
                "contacts": [],
                "campaigns": [],
                "templates": [],
                "messages": [],
                "conversations": [],
                "total": 0,
            },
        )

    results = SearchService.search(business, query)
    return jsonify(success=True, query=query, results=results)