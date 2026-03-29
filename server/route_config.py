"""Decorator for route configuration metadata."""

from functools import wraps
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def route_config(
    httpMethod: str,
    jwtRequired: bool = False,
    createAccessToken: bool = False,
    successMessage: str | None = None,
) -> Callable[[F], F]:
    """
    Decorator that attaches route metadata to action methods.
    
    Args:
        httpMethod: HTTP method ('GET', 'POST', 'PATCH', 'DELETE', etc.)
        jwtRequired: Whether JWT authentication is required
        createAccessToken: Whether to create a new token on successful response
        successMessage: Message to include in success response
    """
    def decorator(func: F) -> F:
        func.route_config = {
            "httpMethod": httpMethod,
            "jwtRequired": jwtRequired,
            "createAccessToken": createAccessToken,
            "successMessage": successMessage,
        }
        return func
    return decorator
