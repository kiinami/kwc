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


def test_healthz_is_exempt(client):
    assert client.get("/healthz").status_code == 200


def test_logged_in_user_can_access(auth_client):
    assert auth_client.get("/").status_code == 200
