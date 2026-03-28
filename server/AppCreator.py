from __future__ import annotations

from pathlib import Path
import sys

from flask import Flask
from flask_cors import CORS

SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from ApiRequest import ApiRequests
from Object import allowedDevOrigins


class AppCreator:
    """Builds the Flask app and can generate the bootstrap App.py file."""

    def __init__(self, apiRequests: ApiRequests) -> None:
        self.apiRequests = apiRequests

    def create_app(self) -> Flask:
        app = Flask(__name__)
        app.config["JSON_SORT_KEYS"] = False

        CORS(
            app,
            resources={r"/api/*": {"origins": list(allowedDevOrigins)}},
            supports_credentials=True,
        )

        self.apiRequests.register(app)
        return app

    def build_app_file_content(self) -> str:
        return """from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from AppCreator import AppCreator
from ApiRequest import ApiRequests, getServices


def create_app():
    return AppCreator(
        apiRequests=ApiRequests(services_provider=lambda: getServices())
    ).create_app()


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
"""

    def generate_app_file(self, output_path: str | Path | None = None) -> Path:
        target = Path(output_path) if output_path else SERVER_DIR / "App.py"
        target.write_text(self.build_app_file_content(), encoding="utf-8")
        return target

    def generateAPI(self, kind: str = "app") -> Path:
        if kind != "app":
            raise ValueError('Only "app" generation is supported in this project.')
        return self.generate_app_file()


if __name__ == "__main__":
    creator = AppCreator(apiRequests=ApiRequests())
    generated_path = creator.generate_app_file()
    print(f"Generated {generated_path.name}")
