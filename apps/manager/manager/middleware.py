from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

from .adapters import is_allowed

_EXEMPT_PREFIXES = ("/accounts/", "/healthz", "/static/")


class ManagerLoginRequiredMiddleware:
    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(_EXEMPT_PREFIXES):
            return self.get_response(request)
        login = reverse("account_login")
        if not request.user.is_authenticated:
            return redirect(f"{login}?next={request.path}")
        if not is_allowed(request.user.email):
            logout(request)
            return redirect(f"{login}?next={request.path}")
        return self.get_response(request)
