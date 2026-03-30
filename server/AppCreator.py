from __future__ import annotations

import inspect
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent


class AppCreator:
    """Generate the Flask runtime app from ApiRequests route metadata."""

    def __init__(self, api_requests_class=None, output_file: str | Path | None = None) -> None:
        if api_requests_class is None:
            from ApiRequest import ApiRequests

            api_requests_class = ApiRequests

        self.api_requests_class = api_requests_class
        self.output_file = Path(output_file) if output_file else SERVER_DIR / "app.py"

    def _get_route_methods(self) -> list[tuple[str, inspect.Signature, dict[str, object]]]:
        methods: list[tuple[str, inspect.Signature, dict[str, object]]] = []
        for name, method in inspect.getmembers(self.api_requests_class, predicate=inspect.isfunction):
            route_details = getattr(method, "route_config", None)
            if route_details:
                methods.append((name, inspect.signature(method), route_details))
        return methods

    def _get_route_path(self, method_name: str, route_config: dict[str, object]) -> str:
        route_path = route_config.get("routePath")
        if isinstance(route_path, str) and route_path.strip():
            return route_path.strip()
        return f"/api/{method_name}"

    @staticmethod
    def _extract_parameters(signature: inspect.Signature) -> list[inspect.Parameter]:
        return [parameter for name, parameter in signature.parameters.items() if name != "self"]

    @staticmethod
    def _url_parameters(route_path: str) -> list[str]:
        parameters: list[str] = []
        chunks = route_path.split("<")
        for chunk in chunks[1:]:
            parameters.append(chunk.split(">", 1)[0])
        return parameters

    @staticmethod
    def _quote(value: object) -> str:
        return repr(value)

    def _generate_route_handler(self, method_name: str, signature: inspect.Signature, route_config: dict[str, object]) -> str:
        http_method = str(route_config["httpMethod"])
        auth_required = bool(route_config.get("authRequired", route_config.get("jwtRequired", False)))
        create_token = bool(route_config.get("createAccessToken", False))
        delete_cookie = bool(route_config.get("deleteCookie", False))
        permission_error_status_code = int(route_config.get("permissionErrorStatusCode", 403))
        success_message = route_config.get("successMessage")
        route_path = self._get_route_path(method_name, route_config)
        parameters = self._extract_parameters(signature)
        url_parameters = self._url_parameters(route_path)
        handler_name = f"handle_{method_name}"
        status_code = int(route_config.get("statusCode", 200))

        lines: list[str] = []
        lines.append(f"@app.route({self._quote(route_path)}, methods=[{self._quote(http_method)}])")
        handler_args = ", ".join(url_parameters)
        lines.append(f"def {handler_name}({handler_args}):" if handler_args else f"def {handler_name}():")
        lines.append("    payload = request.get_json(silent=True) or {}")
        lines.append("    try:")
        lines.append("        session = None")
        lines.append("        token = request.cookies.get(sessionCookieName, '')")

        if auth_required:
            lines.append("        session = api_requests.services.auth.getSession(token)")
            lines.append("        if session is None:")
            lines.append("            return json_error('Authentication required.', 401)")
            lines.append("        current_user = session.user.id")
        elif any(parameter.name in {"token", "userId"} for parameter in parameters):
            lines.append("        if token:")
            lines.append("            session = api_requests.services.auth.getSession(token)")

        call_arguments: list[str] = []
        for parameter in parameters:
            name = parameter.name
            if name in url_parameters:
                call_arguments.append(name)
                continue
            if name == "token":
                call_arguments.append("token")
                continue
            if name == "userId":
                if auth_required:
                    lines.append("        userId = payload.get('userId', current_user)")
                    call_arguments.append("userId")
                    continue
                lines.append("        userId = payload.get('userId')")
                call_arguments.append("userId")
                continue
            default = None if parameter.default is inspect._empty else parameter.default
            if default is None:
                lines.append(f"        {name} = payload.get({self._quote(name)})")
            else:
                lines.append(f"        {name} = payload.get({self._quote(name)}, {self._quote(default)})")
            call_arguments.append(name)

        if auth_required and "userId" in [parameter.name for parameter in parameters]:
            lines.append("        if userId != current_user:")
            lines.append("            raise PermissionError('You do not have permission to access this resource.')")

        lines.append(f"        result = api_requests.{method_name}({', '.join(call_arguments)})")
        message_value = self._quote(success_message) if success_message else "None"
        lines.append(f"        response = build_api_response(result, success_message={message_value})")

        if create_token:
            lines.append("        token_value = response.get_json().get('token', '')")
            lines.append("        if token_value:")
            lines.append("            response.set_cookie(")
            lines.append("                sessionCookieName,")
            lines.append("                token_value,")
            lines.append("                httponly=True,")
            lines.append("                samesite='Lax',")
            lines.append("                secure=False,")
            lines.append("                max_age=30 * 24 * 60 * 60,")
            lines.append("            )")

        if delete_cookie:
            lines.append("        response.delete_cookie(sessionCookieName, httponly=True, samesite='Lax', secure=False)")

        lines.append(f"        return response, {status_code}")
        lines.append("    except PermissionError as error:")
        lines.append(f"        return json_error(str(error), {permission_error_status_code})")
        lines.append("    except ValidationError as error:")
        lines.append("        return json_error(error.errors()[0]['msg'], 400)")
        lines.append("    except DuplicateEmailError as error:")
        lines.append("        return json_error(str(error), 409)")
        lines.append("    except ValueError as error:")
        lines.append("        return json_error(str(error), 400)")
        lines.append("    except Exception as error:")
        lines.append("        return json_error(str(error), 500)")
        return "\n".join(lines)

    def generate_app_code(self) -> str:
        handlers = [
            self._generate_route_handler(method_name, signature, route_details)
            for method_name, signature, route_details in self._get_route_methods()
        ]
        handler_code = "\n\n\n".join(handlers)
        return f'''"""Generated by AppCreator. Do not edit by hand."""

from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from pydantic import ValidationError

SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from ApiRequest import ApiRequests, DuplicateEmailError, getServices
from Object import allowedDevOrigins, sessionCookieName

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

CORS(
    app,
    resources={{r"/api/*": {{"origins": list(allowedDevOrigins)}}}},
    supports_credentials=True,
)

api_requests = ApiRequests(services_provider=getServices)


def build_api_payload(result, success_message=None):
    if isinstance(result, dict):
        payload = dict(result)
    else:
        payload = {{"data": result}}
    if success_message:
        payload.setdefault("message", success_message)
    return payload


def build_api_response(result, success_message=None):
    return jsonify(build_api_payload(result, success_message=success_message))


def json_error(message, status_code):
    return jsonify({{"error": message}}), status_code


{handler_code}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
'''

    def generate_app_file(self, output_path: str | Path | None = None) -> Path:
        target = Path(output_path) if output_path else self.output_file
        target.write_text(self.generate_app_code(), encoding="utf-8")
        return target

    def generateAPI(self, kind: str = "app") -> Path:
        if kind != "app":
            raise ValueError('Only "app" generation is supported in this project.')
        return self.generate_app_file()


if __name__ == "__main__":
    creator = AppCreator()
    generated_path = creator.generateAPI("app")
    print(f"Generated {generated_path}")
