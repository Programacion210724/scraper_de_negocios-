import pytest
from unittest.mock import patch, MagicMock, AsyncMock

def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200

def test_scrape_no_data_returns_400(client):
    resp = client.post("/api/scrape", json={})
    assert resp.status_code == 400

def test_scrape_missing_fields_returns_400(client):
    resp = client.post("/api/scrape", json={"keyword": "Dentistas"})
    assert resp.status_code == 400

def test_scrape_invalid_limit_returns_400(client):
    resp = client.post("/api/scrape", json={
        "keyword": "Dentistas", "city": "Madrid", "limit": -1
    })
    assert resp.status_code == 400

def test_scrape_success(client, sample_results, monkeypatch):
    monkeypatch.setattr("asyncio.run", lambda coro, **kwargs: sample_results)
    resp = client.post("/api/scrape", json={
        "keyword": "Dentistas", "city": "Madrid", "limit": 10
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert len(data["data"]) == 2
    assert data["data"][0]["nombre"] == "Clínica Dental Madrid"

def test_download_no_data_returns_400(client):
    resp = client.post("/api/download", json={})
    assert resp.status_code == 400

def test_download_empty_results_returns_400(client):
    resp = client.post("/api/download", json={"results": []})
    assert resp.status_code == 400

def test_download_success(client, sample_results):
    resp = client.post("/api/download", json={"results": sample_results})
    assert resp.status_code == 200
    assert resp.content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

def test_cancel_returns_success(client):
    resp = client.post("/api/cancel")
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

def test_save_to_sheets_no_data_returns_400(client):
    resp = client.post("/api/save-to-sheets", json={})
    assert resp.status_code == 400

def test_save_to_sheets_empty_results_returns_400(client):
    resp = client.post("/api/save-to-sheets", json={"results": []})
    assert resp.status_code == 400
