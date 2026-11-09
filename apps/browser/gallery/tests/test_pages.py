def test_takedown_page_uses_configured_email(client, settings):
    settings.KWC_TAKEDOWN_EMAIL = "rights@example.com"
    response = client.get("/takedown")
    assert response.status_code == 200
    assert b"rights@example.com" in response.content


def test_takedown_page_hides_missing_email(client, settings):
    settings.KWC_TAKEDOWN_EMAIL = ""
    response = client.get("/takedown")
    assert b"mailto:" not in response.content
