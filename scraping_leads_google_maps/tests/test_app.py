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
    from modelos.lead import Lead
    
    def dict_to_lead(d):
        return Lead(
            nombre=d.get("nombre", ""),
            direccion=d.get("direccion", ""),
            telefono=d.get("telefono", ""),
            ciudad=d.get("ciudad", ""),
            categoria_busqueda=d.get("categoria", ""),
            url_raw=d.get("maps_url", ""),
            fuente="google_maps",
            maps_url=d.get("maps_url", ""),
            categoria_pred=None,
            confianza=None,
            job_id="",
        )
    
    sample_leads = [dict_to_lead(d) for d in sample_results]
    
    with patch("fuentes.google_maps.GoogleMapsSource.scrape", return_value=sample_leads):
        resp = client.post("/api/scrape", json={
            "keyword": "Dentistas", "city": "Madrid", "limit": 10
        })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert len(data["data"]) == 2
    assert data["data"][0]["nombre"] == "Clínica Dental Madrid"
    # Formato legacy: 'categoria' no 'categoria_busqueda'
    assert "categoria" in data["data"][0]
    assert "categoria_busqueda" not in data["data"][0]

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
