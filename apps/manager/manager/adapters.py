from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.http import HttpResponseForbidden


def is_allowed(email: str | None) -> bool:
    if not email:
        return False
    allowed = {item.casefold() for item in settings.MANAGER_ALLOWED_EMAILS}
    return email.casefold() in allowed


class ManagerAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request) -> bool:
        return False

    def pre_login(self, request, user, **kwargs):
        if not is_allowed(user.email):
            raise ImmediateHttpResponse(HttpResponseForbidden("This account is not allowed."))
        return super().pre_login(request, user, **kwargs)


class ManagerSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_allowed(self, email: str | None) -> bool:
        return is_allowed(email)

    def pre_social_login(self, request, sociallogin) -> None:
        email = sociallogin.user.email or sociallogin.account.extra_data.get("email", "")
        if not is_allowed(email):
            raise ImmediateHttpResponse(HttpResponseForbidden("This account is not allowed."))
