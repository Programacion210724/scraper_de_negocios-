"""Tests del adapter GoogleMapsSource.

Verifica que:
  - El adapter importa scrape_google_maps del core (read-only)
  - Convierte dict[] del core en Lead[] correctamente
  - Mapea todos los campos segun el plan (categoria -> categoria_busqueda, etc.)
  - No modifica el core
"""
import pytest
from unittest.mock import AsyncMock, patch

from modelos.lead import Lead
from modelos.scrape_request import ScrapeRequest
from fuentes.google_maps import GoogleMapsSource


@pytest.fixture
def source():
    return GoogleMapsSource()


@pytest.fixture
def sample_raw_results():
    """Simula el output de scrape_google_maps del core."""
    return [
        {
            "nombre": "Café A",
            "direccion": "Av. Arequipa 123, Lima",
            "telefono": "+51 999 123 456",
            "ciudad": "Lima",
            "categoria": "Cafeterías",
            "maps_url": "https://maps.google.com/place/cafe-a",
            "categoria_pred": "restaurante",
            "confianza": 0.95,
        },
        {
            "nombre": "Café B",
            "direccion": "Av. Brasil 456, Lima",
            "telefono": "+51 987 654 321",
            "ciudad": "Lima",
            "categoria": "Cafeterías",
            "maps_url": "https://maps.google.com/place/cafe-b",
            "categoria_pred": "restaurante",
            "confianza": 0.88,
        },
    ]


# --- Propiedades de la fuente ---

def test_source_name(source):
    assert source.source_name == "google_maps"


def test_source_config(source):
    config = source.source_config
    assert config.display_name == "Google Maps"
    assert config.priority == 10
    assert config.country == "PE"
    assert config.requires_proxy is True
    assert config.enabled is True
    assert config.supports_deep is True


def test_build_search_url(source):
    url = source.build_search_url("Cafeterías", "Lima")
    assert "google.com/maps/search" in url
    assert "Lima" in url


def test_get_metadata(source):
    metadata = source.get_metadata()
    assert isinstance(metadata, dict)
    assert "captcha_required" in metadata


# --- scrape() ---

@pytest.mark.asyncio
async def test_scrape_devuelve_lista_de_leads(source, sample_raw_results):
    request = ScrapeRequest(keyword="Cafeterías", city="Lima", limit=10)
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = sample_raw_results
        leads = await source.scrape(request, None)

    assert len(leads) == 2
    assert all(isinstance(l, Lead) for l in leads)


@pytest.mark.asyncio
async def test_scrape_mapea_campos_del_core(source, sample_raw_results):
    """Verifica el mapeo: categoria -> categoria_busqueda, etc."""
    request = ScrapeRequest(keyword="Cafeterías", city="Lima", limit=10)
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = sample_raw_results
        leads = await source.scrape(request, None)

    lead = leads[0]
    # Campos directos
    assert lead.nombre == "Café A"
    assert lead.direccion == "Av. Arequipa 123, Lima"
    assert lead.telefono == "+51 999 123 456"
    assert lead.ciudad == "Lima"
    # categoria -> categoria_busqueda (rename)
    assert lead.categoria_busqueda == "Cafeterías"
    # maps_url -> url_raw + maps_url (dual)
    assert lead.url_raw == "https://maps.google.com/place/cafe-a"
    assert lead.maps_url == "https://maps.google.com/place/cafe-a"
    # ML fields
    assert lead.categoria_pred == "restaurante"
    assert lead.confianza == 0.95
    # fuente hardcodeada
    assert lead.fuente == "google_maps"


@pytest.mark.asyncio
async def test_scrape_field_sources_todos_de_google_maps(source, sample_raw_results):
    request = ScrapeRequest(keyword="Cafeterías", city="Lima", limit=10)
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = sample_raw_results
        leads = await source.scrape(request, None)

    lead = leads[0]
    assert lead.field_sources.get("nombre") == "google_maps"
    assert lead.field_sources.get("telefono") == "google_maps"
    assert lead.field_sources.get("direccion") == "google_maps"
    assert lead.field_sources.get("categoria_busqueda") == "google_maps"


@pytest.mark.asyncio
async def test_scrape_raw_fields_almacena_dict_original(source, sample_raw_results):
    request = ScrapeRequest(keyword="Cafeterías", city="Lima", limit=10)
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = sample_raw_results
        leads = await source.scrape(request, None)

    lead = leads[0]
    assert "google_maps" in lead.raw_fields
    assert lead.raw_fields["google_maps"]["nombre"] == "Café A"
    assert lead.raw_fields["google_maps"]["maps_url"] == "https://maps.google.com/place/cafe-a"


@pytest.mark.asyncio
async def test_scrape_resultados_vacios(source):
    request = ScrapeRequest(keyword="X", city="Y", limit=10)
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = []
        leads = await source.scrape(request, None)

    assert leads == []
    mock_scrape.assert_called_once()


@pytest.mark.asyncio
async def test_scrape_pasa_parametros_correctos(source):
    """Verifica que el adapter pasa keyword, city, limit, mode, cancel_event."""
    request = ScrapeRequest(keyword="Cafeterías", city="Lima", limit=50, mode="deep")
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = []
        await source.scrape(request, None)

    mock_scrape.assert_called_once_with(
        keyword="Cafeterías",
        city="Lima",
        limit=50,
        mode="deep",
        cancel_event=None,
    )


@pytest.mark.asyncio
async def test_scrape_pasa_cancel_event(source):
    """Verifica que el cancel_event se propaga al core."""
    import threading
    request = ScrapeRequest(keyword="Test", city="Lima", limit=10)
    cancel = threading.Event()
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.return_value = []
        await source.scrape(request, cancel)

    mock_scrape.assert_called_once_with(
        keyword="Test",
        city="Lima",
        limit=10,
        mode="simple",
        cancel_event=cancel,
    )


@pytest.mark.asyncio
async def test_scrape_wrappa_errores_en_source_error(source):
    """Errores del core se envuelven en SourceError."""
    request = ScrapeRequest(keyword="Test", city="Lima", limit=10)
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.side_effect = RuntimeError("Error inesperado del navegador")
        with pytest.raises(Exception):
            await source.scrape(request, None)


@pytest.mark.asyncio
async def test_scrape_wrappa_captcha_en_captcha_error(source):
    """Errores de captcha se envuelven en CaptchaError."""
    from excepciones.source_errors import CaptchaError
    request = ScrapeRequest(keyword="Test", city="Lima", limit=10)
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.side_effect = RuntimeError("Captcha detectado en la pagina")
        with pytest.raises(CaptchaError) as exc_info:
            await source.scrape(request, None)
    assert exc_info.value.source == "google_maps"
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_scrape_wrappa_timeout_en_source_timeout(source):
    """Errores de timeout se envuelven en SourceTimeoutError."""
    from excepciones.source_errors import SourceTimeoutError
    request = ScrapeRequest(keyword="Test", city="Lima", limit=10)
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock_scrape:
        mock_scrape.side_effect = RuntimeError("timeout esperando respuesta del servidor")
        with pytest.raises(SourceTimeoutError) as exc_info:
            await source.scrape(request, None)
    assert exc_info.value.source == "google_maps"
    assert exc_info.value.retryable is True
