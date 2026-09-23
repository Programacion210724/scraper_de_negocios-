"""Tests de integracion API V2: /api/scrape con pipeline Orquestador -> ScraperFactory -> GoogleMapsSource.

Verifica:
  - El endpoint llama al Orquestador (no al core directamente)
  - ScrapeRequest se construye correctamente con los parametros del API
  - El registry de Google Maps esta activo
  - La respuesta usa el formato legacy (categoria, no categoria_busqueda)
  - El cancel_event se propaga
  - Mapeo de errores HTTP: SourceTimeoutError->504, CaptchaError->503, SourceError->502
"""
import asyncio
import threading
import pytest
from unittest.mock import AsyncMock, patch

import fuentes  # noqa: F401 — activa registry
from modelos.scrape_request import ScrapeRequest
from servicios.fabrica_scrapers import ScraperFactory
from excepciones.source_errors import SourceError, CaptchaError, SourceTimeoutError


SAMPLE_RAW = [
    {
        "nombre": "Clínica Dental Madrid",
        "direccion": "Calle Mayor 10, Madrid",
        "telefono": "+34 912 345 678",
        "ciudad": "Madrid",
        "categoria": "Dentistas",
        "maps_url": "https://maps.google.com/place/abc123",
        "categoria_pred": "salud",
        "confianza": 0.95,
    },
    {
        "nombre": "Dentistas López",
        "direccion": "Av. de la Constitución 25, Madrid",
        "telefono": "+34 911 234 567",
        "ciudad": "Madrid",
        "categoria": "Dentistas",
        "maps_url": "https://maps.google.com/place/def456",
        "categoria_pred": "salud",
        "confianza": 0.90,
    },
]


@pytest.fixture
def mock_source():
    """Mock de scrape_google_maps para no hacer scraping real."""
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock:
        mock.return_value = SAMPLE_RAW
        yield mock


# --- Tests de integracion del pipeline completo ---

def test_scrape_v2_responde_success_con_datos(client, mock_source):
    """El endpoint V2 devuelve {success: True, data: [...]} en formato legacy."""
    resp = client.post("/api/scrape", json={
        "keyword": "Dentistas", "city": "Madrid", "limit": 10
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert len(data["data"]) == 2


def test_scrape_v2_formato_legacy_categoria(client, mock_source):
    """La respuesta usa 'categoria' (legacy), no 'categoria_busqueda'."""
    resp = client.post("/api/scrape", json={
        "keyword": "Dentistas", "city": "Madrid", "limit": 10
    })
    data = resp.get_json()
    for item in data["data"]:
        assert "categoria" in item
        assert "categoria_busqueda" not in item


def test_scrape_v2_campos_legacy_presentes(client, mock_source):
    """Todos los 8 campos legacy estan presentes en cada lead."""
    resp = client.post("/api/scrape", json={
        "keyword": "Dentistas", "city": "Madrid", "limit": 10
    })
    data = resp.get_json()
    expected_keys = {
        "nombre", "direccion", "telefono", "ciudad",
        "categoria", "maps_url", "categoria_pred", "confianza",
    }
    for item in data["data"]:
        assert set(item.keys()) == expected_keys


def test_scrape_v2_categoria_Proviente_de_categoria_busqueda(client, mock_source):
    """categoria en la respuesta proviene de categoria_busqueda del Lead."""
    resp = client.post("/api/scrape", json={
        "keyword": "Dentistas", "city": "Madrid", "limit": 10
    })
    data = resp.get_json()
    assert data["data"][0]["categoria"] == "Dentistas"


# --- Tests de construccion de ScrapeRequest ---

def test_scrape_v2_construye_scrape_request_correctamente(client):
    """Verifica que ScrapeRequest se construye con keyword, city, limit, mode."""
    captured = {}

    async def fake_orquestar(request, cancel_event=None):
        captured["request"] = request
        captured["cancel_event"] = cancel_event
        return []

    with patch("app.Orquestador") as MockOrquestador:
        instance = MockOrquestador.return_value
        instance.orquestar = AsyncMock(side_effect=fake_orquestar)
        resp = client.post("/api/scrape", json={
            "keyword": "Cafeterias", "city": "Lima", "limit": 50, "mode": "deep"
        })

    assert resp.status_code == 200
    req = captured["request"]
    assert isinstance(req, ScrapeRequest)
    assert req.keyword == "Cafeterias"
    assert req.city == "Lima"
    assert req.limit == 50
    assert req.mode == "deep"
    assert req.source == "google_maps"


def test_scrape_v2_limit_max_100(client):
    """El límite se capa en 100."""
    captured = {}

    async def fake_orquestar(request, cancel_event=None):
        captured["limit"] = request.limit
        return []

    with patch("app.Orquestador") as MockOrquestador:
        instance = MockOrquestador.return_value
        instance.orquestar = AsyncMock(side_effect=fake_orquestar)
        resp = client.post("/api/scrape", json={
            "keyword": "Test", "city": "Lima", "limit": 500
        })

    assert resp.status_code == 200
    assert captured["limit"] == 100


def test_scrape_v2_limit_default_20(client):
    """El límite por defecto es 20."""
    captured = {}

    async def fake_orquestar(request, cancel_event=None):
        captured["limit"] = request.limit
        return []

    with patch("app.Orquestador") as MockOrquestador:
        instance = MockOrquestador.return_value
        instance.orquestar = AsyncMock(side_effect=fake_orquestar)
        resp = client.post("/api/scrape", json={
            "keyword": "Test", "city": "Lima"
        })

    assert resp.status_code == 200
    assert captured["limit"] == 20


def test_scrape_v2_propaga_cancel_event(client):
    """El cancel_event del módulo se pasa al Orquestador."""
    captured = {}

    async def fake_orquestar(request, cancel_event=None):
        captured["cancel_event"] = cancel_event
        return []

    with patch("app.Orquestador") as MockOrquestador:
        instance = MockOrquestador.return_value
        instance.orquestar = AsyncMock(side_effect=fake_orquestar)
        resp = client.post("/api/scrape", json={
            "keyword": "Test", "city": "Lima", "limit": 10
        })

    assert resp.status_code == 200
    assert captured["cancel_event"] is not None
    assert isinstance(captured["cancel_event"], threading.Event)


# --- Tests de registry desde contexto de app ---

def test_scrape_v2_registry_activo_desde_app():
    """El import de app activa el registry de GoogleMapsSource."""
    assert "google_maps" in ScraperFactory.list_sources()
    source = ScraperFactory.get("google_maps")
    assert source.source_name == "google_maps"


# --- Tests de resultados vacios y cancelacion ---

def test_scrape_v2_resultados_vacios(client):
    """Si el scraping devuelve vacio, la respuesta es {success: True, data: []}."""
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = []
        resp = client.post("/api/scrape", json={
            "keyword": "Test", "city": "Lima", "limit": 10
        })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"] == []


# --- Tests de mapeo de errores HTTP ---

def test_scrape_error_source_timeout_504(client):
    """SourceTimeoutError -> 504 Gateway Timeout."""
    from excepciones.source_errors import SourceTimeoutError

    async def raise_timeout(request, cancel_event=None):
        raise SourceTimeoutError("google_maps", "Timeout agotado")

    with patch("app.Orquestador") as MockOrquestador:
        instance = MockOrquestador.return_value
        instance.orquestar = AsyncMock(side_effect=raise_timeout)
        resp = client.post("/api/scrape", json={
            "keyword": "Test", "city": "Lima", "limit": 10
        })

    assert resp.status_code == 504
    data = resp.get_json()
    assert "error" in data


def test_scrape_error_captcha_503(client):
    """CaptchaError -> 503 Service Unavailable."""
    from excepciones.source_errors import CaptchaError

    async def raise_captcha(request, cancel_event=None):
        raise CaptchaError("google_maps", "Captcha detectado")

    with patch("app.Orquestador") as MockOrquestador:
        instance = MockOrquestador.return_value
        instance.orquestar = AsyncMock(side_effect=raise_captcha)
        resp = client.post("/api/scrape", json={
            "keyword": "Test", "city": "Lima", "limit": 10
        })

    assert resp.status_code == 503
    data = resp.get_json()
    assert "error" in data


def test_scrape_error_source_error_502(client):
    """SourceError (no timeout/captcha) -> 502 Bad Gateway."""
    async def raise_source_error(request, cancel_event=None):
        raise SourceError("google_maps", "Error de conexion", retryable=False)

    with patch("app.Orquestador") as MockOrquestador:
        instance = MockOrquestador.return_value
        instance.orquestar = AsyncMock(side_effect=raise_source_error)
        resp = client.post("/api/scrape", json={
            "keyword": "Test", "city": "Lima", "limit": 10
        })

    assert resp.status_code == 502
    data = resp.get_json()
    assert "error" in data
    assert "google_maps" in data["error"]


def test_scrape_error_unexpected_500(client):
    """Exception inesperada -> 500 Internal Server Error."""
    async def raise_unexpected(request, cancel_event=None):
        raise RuntimeError("Error inesperado del servidor")

    with patch("app.Orquestador") as MockOrquestador:
        instance = MockOrquestador.return_value
        instance.orquestar = AsyncMock(side_effect=raise_unexpected)
        resp = client.post("/api/scrape", json={
            "keyword": "Test", "city": "Lima", "limit": 10
        })

    assert resp.status_code == 500
    data = resp.get_json()
    assert "error" in data


def test_scrape_error_asyncio_timeout_504(client):
    """asyncio.TimeoutError (600s) -> 504 Gateway Timeout."""
    async def raise_timeout(request, cancel_event=None):
        raise asyncio.TimeoutError()

    with patch("app.Orquestador") as MockOrquestador:
        instance = MockOrquestador.return_value
        instance.orquestar = AsyncMock(side_effect=raise_timeout)
        resp = client.post("/api/scrape", json={
            "keyword": "Test", "city": "Lima", "limit": 10
        })

    assert resp.status_code == 504
    data = resp.get_json()
    assert "error" in data


# --- Tests de validacion de entrada (sin cambio de comportamiento) ---

def test_scrape_v2_no_data_returns_400(client):
    resp = client.post("/api/scrape", json={})
    assert resp.status_code == 400


def test_scrape_v2_missing_fields_returns_400(client):
    resp = client.post("/api/scrape", json={"keyword": "Dentistas"})
    assert resp.status_code == 400


def test_scrape_v2_invalid_limit_returns_400(client):
    resp = client.post("/api/scrape", json={
        "keyword": "Dentistas", "city": "Madrid", "limit": -1
    })
    assert resp.status_code == 400


def test_scrape_v2_limit_string_invalid_returns_400(client):
    resp = client.post("/api/scrape", json={
        "keyword": "Dentistas", "city": "Madrid", "limit": "abc"
    })
    assert resp.status_code == 400
