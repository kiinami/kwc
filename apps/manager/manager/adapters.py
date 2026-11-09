from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.http import HttpResponseForbidden


class ManagerSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_allowed(self, email: str | None) -> bool:
        if not email:
            return False
        allowed = {item.casefold() for item in settings.MANAGER_ALLOWED_EMAILS}
        return email.casefold() in allowed

    def pre_social_login(self, request, sociallogin) -> None:
        email = sociallogin.user.email or sociallogin.account.extra_data.get("email", "")
        if not self.is_allowed(email):
            raise ImmediateHttpResponse(HttpResponseForbidden("This account is not allowed."))
