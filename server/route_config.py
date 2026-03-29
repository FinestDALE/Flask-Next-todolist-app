"""Decorator for route configuration metadata."""

from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def route_config(
    httpMethod: str,
    jwtRequired: bool | None = None,
    authRequired: bool | None = None,
    createAccessToken: bool = False,
    successMessage: str | None = None,
    routePath: str | None = None,
) -> Callable[[F], F]:
    """
    Decorator that attaches route metadata to action methods.
    
    Args:
        httpMethod: HTTP method ('GET', 'POST', 'PATCH', 'DELETE', etc.)
        jwtRequired: Backward-compatible auth flag
        authRequired: Preferred auth-required flag for generated routes
        createAccessToken: Whether to create a new token on successful response
        successMessage: Message to include in success response
        routePath: Explicit API route path for the generated handler
    """
    def decorator(func: F) -> F:
        effective_auth_required = authRequired if authRequired is not None else bool(jwtRequired)
        func.route_config = {
            "httpMethod": httpMethod,
            "jwtRequired": effective_auth_required,
            "authRequired": effective_auth_required,
            "createAccessToken": createAccessToken,
            "successMessage": successMessage,
            "routePath": routePath,
        }
        return func
    return decorator
