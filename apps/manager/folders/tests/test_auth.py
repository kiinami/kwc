from types import SimpleNamespace

import pytest

from manager.adapters import ManagerSocialAccountAdapter


@pytest.mark.django_db
def test_manager_requires_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/accounts/" in response.url


def test_allowlist_is_case_insensitive(settings):
    settings.MANAGER_ALLOWED_EMAILS = ["owner@example.com"]
    adapter = ManagerSocialAccountAdapter()
    assert adapter.is_allowed("OWNER@example.com")
    assert not adapter.is_allowed("stranger@example.com")


def test_empty_allowlist_denies_everyone(settings):
    settings.MANAGER_ALLOWED_EMAILS = []
    assert not ManagerSocialAccountAdapter().is_allowed("owner@example.com")


def sociallogin(email: str) -> SimpleNamespace:
    return SimpleNamespace(
        user=SimpleNamespace(email=email),
        account=SimpleNamespace(extra_data={"email": email}),
    )


def test_social_signup_is_open_for_allowlisted_email(settings):
    settings.MANAGER_ALLOWED_EMAILS = ["owner@example.com"]
    adapter = ManagerSocialAccountAdapter()
    assert adapter.is_open_for_signup(None, sociallogin("owner@example.com"))


def test_social_signup_is_closed_for_other_emails(settings):
    settings.MANAGER_ALLOWED_EMAILS = ["owner@example.com"]
    adapter = ManagerSocialAccountAdapter()
    assert not adapter.is_open_for_signup(None, sociallogin("stranger@example.com"))


def test_healthz_is_exempt(client):
    assert client.get("/healthz").status_code == 200


def test_logged_in_user_can_access(auth_client):
    assert auth_client.get("/").status_code == 200


@pytest.mark.django_db
def test_local_signup_is_disabled(client, django_user_model):
    client.post(
        "/accounts/signup/",
        {
            "username": "intruder",
            "email": "intruder@example.com",
            "password1": "Passw0rd!intruder",
            "password2": "Passw0rd!intruder",
        },
    )
    assert not django_user_model.objects.filter(username="intruder").exists()


@pytest.mark.django_db
def test_non_allowlisted_authenticated_user_is_rejected(client, django_user_model, settings):
    settings.MANAGER_ALLOWED_EMAILS = ["owner@example.com"]
    user = django_user_model.objects.create_user(
        username="stranger",
        email="stranger@example.com",
        password="test-password",
    )
    client.force_login(user)
    assert client.get("/").status_code == 302
