from __future__ import annotations

import json

import pytest
from django.urls import reverse

from choose.models import ImageDecision

pytestmark = pytest.mark.django_db(transaction=True)


def test_inbox_decide_route(client) -> None:
    # Test that the inbox/decide endpoint is reachable and works
    folder = "ztmy"
    filename = "ztmy 0001.jpg"
    url = reverse("choose:inbox_decide", kwargs={"folder": folder})
    
    # Normally this URL corresponds to /choose/inbox/ztmy/decide
    # We check if it is resolvable
    assert url == f"/choose/inbox/{folder}/decide"
    
    payload = json.dumps({"filename": filename, "decision": "keep"})
    response = client.post(
        url,
        data=payload,
        content_type="application/json",
    )
    
    assert response.status_code == 200
    assert response.json()["ok"] is True
    
    # Verify decision is saved
    assert ImageDecision.objects.filter(folder=folder, filename=filename, decision="keep").exists()


def test_inbox_save_route_reachable(client, tmp_path, settings) -> None:
    # Test that inbox/save endpoint is reachable
    folder = "ztmy"
    settings.EXTRACTION_FOLDER = tmp_path
    
    url = reverse("choose:inbox_save_api", kwargs={"folder": folder})
    assert url == f"/choose/inbox/{folder}/save"
