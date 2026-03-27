from __future__ import annotations

from flask import Flask, jsonify, make_response, request
from werkzeug.exceptions import HTTPException

from ApiRequest import ApiRequests
from Object import allowedDevOrigins


class AppCreator:
    def __init__(self, apiRequests: ApiRequests | None = None) -> None:
        self.apiRequests = apiRequests or ApiRequests()

    def create_app(self) -> Flask:
        app = Flask(__name__)
        self._register_error_handlers(app)
        self._register_request_hooks(app)
        self.apiRequests.register(app)
        return app

    def _register_error_handlers(self, app: Flask) -> None:
        @app.errorhandler(Exception)
        def handleUnexpectedError(error: Exception):
            if isinstance(error, HTTPException):
                return jsonify({"error": error.description}), error.code
            app.logger.exception("Unhandled application error: %s", error)
            return jsonify({"error": "Something went wrong on the server. Please try again."}), 500

    def _register_request_hooks(self, app: Flask) -> None:
        @app.after_request
        def addCorsHeaders(response):
            origin = request.headers.get("Origin", "")
            response.headers["Access-Control-Allow-Origin"] = (
                origin if origin in allowedDevOrigins else "http://localhost:3000"
            )
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
            return response

        @app.before_request
        def handleOptions():
            if request.method == "OPTIONS":
                return make_response("", 204)
            return None


def create_app(apiRequests: ApiRequests | None = None) -> Flask:
    return AppCreator(apiRequests=apiRequests).create_app()
