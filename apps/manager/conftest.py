import pytest


@pytest.fixture
def auth_client(client, django_user_model, db, settings):
    settings.MANAGER_ALLOWED_EMAILS = ["owner@example.com"]
    user = django_user_model.objects.create_user(
        username="owner",
        email="owner@example.com",
        password="test-password",
    )
    client.force_login(user)
    return client
