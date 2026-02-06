import pytest
from django.urls import reverse


@pytest.fixture
def mock_extraction_folder(settings, tmp_path):
    # Set settings.EXTRACTION_FOLDER to a tmp path
    settings.EXTRACTION_FOLDER = tmp_path
    return tmp_path


def test_delete_folder_view(client, mock_extraction_folder):
    # Setup
    folder_name = "Test Series (2024)"
    folder_path = mock_extraction_folder / folder_name
    folder_path.mkdir()
    (folder_path / "image.jpg").touch()

    # URL
    url = reverse("choose:inbox_delete", kwargs={"folder": folder_name})

    # Verify folder exists before
    assert folder_path.exists()

    # Action (POST required)
    response = client.post(url)

    # Assert redirect
    assert response.status_code == 302
    assert response.url == reverse("choose:inbox")

    # Assert folder deleted
    assert not folder_path.exists()


def test_delete_folder_view_get_method(client, mock_extraction_folder):
    # Setup
    folder_name = "Test Series (2024)"
    folder_path = mock_extraction_folder / folder_name
    folder_path.mkdir()

    # URL
    url = reverse("choose:inbox_delete", kwargs={"folder": folder_name})

    # Action (GET not allowed)
    response = client.get(url)

    # Assert not allowed
    assert response.status_code == 405

    # Asset folder still exists
    assert folder_path.exists()


def test_delete_folder_not_found(client, mock_extraction_folder):
    url = reverse("choose:inbox_delete", kwargs={"folder": "NonExistent"})
    response = client.post(url)
    assert response.status_code == 404
