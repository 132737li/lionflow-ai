"""
Handlers d'erreurs centralisés.
Retourne du JSON pour les endpoints /api/*, du HTML sinon.
"""
from flask import jsonify, render_template, request
from werkzeug.exceptions import HTTPException


def _wants_json() -> bool:
    return request.path.startswith("/api/") or \
        request.accept_mimetypes.best == "application/json"


def register_error_handlers(app):

    @app.errorhandler(400)
    def bad_request(e):
        if _wants_json():
            return jsonify(success=False, message="Requête invalide",
                           data=None, errors=[str(e)]), 400
        return render_template("errors/404.html", code=400,
                               message="Requête invalide"), 400

    @app.errorhandler(401)
    def unauthorized(e):
        if _wants_json():
            return jsonify(success=False, message="Non authentifié",
                           data=None, errors=[str(e)]), 401
        return render_template("errors/403.html", code=401,
                               message="Non authentifié"), 401

    @app.errorhandler(403)
    def forbidden(e):
        if _wants_json():
            return jsonify(success=False, message="Accès refusé",
                           data=None, errors=[str(e)]), 403
        return render_template("errors/403.html", code=403,
                               message="Accès refusé"), 403

    @app.errorhandler(404)
    def not_found(e):
        if _wants_json():
            return jsonify(success=False, message="Ressource introuvable",
                           data=None, errors=[str(e)]), 404
        return render_template("errors/404.html", code=404,
                               message="Page introuvable"), 404

    @app.errorhandler(413)
    def too_large(e):
        if _wants_json():
            return jsonify(success=False, message="Fichier trop volumineux",
                           data=None, errors=[str(e)]), 413
        return render_template("errors/404.html", code=413,
                               message="Fichier trop volumineux"), 413

    @app.errorhandler(422)
    def unprocessable(e):
        if _wants_json():
            return jsonify(success=False, message="Données invalides",
                           data=None, errors=[str(e)]), 422
        return render_template("errors/404.html", code=422,
                               message="Données invalides"), 422

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Erreur serveur")
        if _wants_json():
            return jsonify(success=False, message="Erreur interne",
                           data=None, errors=[str(e)]), 500
        return render_template("errors/500.html", code=500,
                               message="Erreur interne"), 500

    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        if _wants_json():
            return jsonify(success=False, message=e.description,
                           data=None, errors=[e.name]), e.code
        return render_template("errors/404.html", code=e.code,
                               message=e.description), e.code