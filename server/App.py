from __future__ import annotations

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from AppCreator import AppCreator
from ApiRequest import ApiRequests, getServices


def create_app():
    """Create and configure the Flask application."""
    return AppCreator(
        apiRequests=ApiRequests(services_provider=lambda: getServices())
    ).create_app()


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
