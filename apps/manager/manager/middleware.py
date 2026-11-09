from django.shortcuts import redirect
from django.urls import reverse

_EXEMPT_PREFIXES = ("/accounts/", "/healthz", "/static/")


class ManagerLoginRequiredMiddleware:
    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated or request.path.startswith(_EXEMPT_PREFIXES):
            return self.get_response(request)
        login = reverse("account_login")
        return redirect(f"{login}?next={request.path}")
