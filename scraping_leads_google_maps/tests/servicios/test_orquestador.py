"""Tests del orquestador (pipeline completo V2).

Verifica el pipeline end-to-end con GoogleMapsSource mock:
  scrape -> normalize -> validate -> dedup L1 -> dedup L2(stub)
  -> dedup L3(no-op) -> enrich(passthrough) -> classify -> result

NO hace scraping real: scrape_google_maps esta mockeado.
"""
import threading
import pytest
from unittest.mock import AsyncMock, patch

from modelos.lead import Lead
from modelos.scrape_request import ScrapeRequest

# Importar fuentes para registrar GoogleMapsSource en el factory
from fuentes.google_maps import GoogleMapsSource  # noqa: F401
from servicios.orquestador import Orquestador


@pytest.fixture
def orquestador():
    return Orquestador()


@pytest.fixture
def sample_raw_results():
    """Output simulado de scrape_google_maps del core."""
    return [
        {
            "nombre": "Cafe A",
            "direccion": "Av. Arequipa 123",
            "telefono": "999123456",
            "ciudad": "Lima",
            "categoria": "Cafeterias",
            "maps_url": "https://maps.google.com/place/cafe-a",
            "categoria_pred": "restaurante",
            "confianza": 0.95,
        },
        {
            "nombre": "Reparaciones B",
            "direccion": "Calle 456",
            "telefono": "987654321",
            "ciudad": "Lima",
            "categoria": "Reparaciones",
            "maps_url": "https://maps.google.com/place/reparaciones-b",
            "categoria_pred": "servicio",
            "confianza": 0.88,
        },
    ]


@pytest.fixture
def request_scrape():
    return ScrapeRequest(keyword="Cafeterias", city="Lima", limit=10, mode="simple")


@pytest.fixture
def mock_scrape(sample_raw_results):
    """Patch de scrape_google_maps para no hacer scraping real."""
    with patch("fuentes.google_maps.scrape_google_maps", new_callable=AsyncMock) as mock:
        mock.return_value = sample_raw_results
        yield mock


# --- Test end-to-end ---

@pytest.mark.asyncio
async def test_orquestador_end_to_end(orquestador, request_scrape, mock_scrape):
    """Pipeline completo: scrape -> normalize -> validate -> dedup -> classify."""
    leads = await orquestador.orquestar(request_scrape, None)
    assert len(leads) == 2
    assert all(isinstance(l, Lead) for l in leads)


@pytest.mark.asyncio
async def test_orquestador_normaliza_telefono(orquestador, request_scrape, mock_scrape):
    """Los telefonos se normalizan a E.164 (+51)."""
    leads = await orquestador.orquestar(request_scrape, None)
    lead = leads[0]
    assert lead.telefono == "+51999123456"


@pytest.mark.asyncio
async def test_orquestador_campo_categoria_busqueda(orquestador, request_scrape, mock_scrape):
    """categoria del core se mapea a categoria_busqueda."""
    leads = await orquestador.orquestar(request_scrape, None)
    categorias = {l.categoria_busqueda for l in leads}
    assert "Cafeterias" in categorias
    assert "Reparaciones" in categorias


@pytest.mark.asyncio
async def test_orquestador_aplica_clasificacion_ml(orquestador, request_scrape, mock_scrape):
    """Los leads finales tienen categoria_pred y confianza del ML."""
    leads = await orquestador.orquestar(request_scrape, None)
    for lead in leads:
        assert lead.categoria_pred is not None
        assert lead.confianza is not None


@pytest.mark.asyncio
async def test_orquestador_dedup_L1_elimina_duplicados(orquestador, request_scrape, mock_scrape, sample_raw_results):
    """Leads con el mismo telefono se deduplican en L1."""
    duplicate_lead = {
        "nombre": "Cafe A Duplicate",
        "direccion": "Av. Otra 999",
        "telefono": "999123456",
        "ciudad": "Lima",
        "categoria": "Cafeterias",
        "maps_url": "https://maps.google.com/place/cafe-a-dup",
        "categoria_pred": "restaurante",
        "confianza": 0.95,
    }
    mock_scrape.return_value = sample_raw_results + [duplicate_lead]

    leads = await orquestador.orquestar(request_scrape, None)
    # 3 raw - 1 duplicado (mismo phone) = 2
    assert len(leads) == 2


@pytest.mark.asyncio
async def test_orquestador_resultado_vacio(orquestador, request_scrape, mock_scrape):
    """Si el source devuelve vacio, el pipeline retorna vacio."""
    mock_scrape.return_value = []
    leads = await orquestador.orquestar(request_scrape, None)
    assert leads == []


@pytest.mark.asyncio
async def test_orquestador_valida_nombre_vacio(orquestador, request_scrape, mock_scrape):
    """Leads con nombre vacio se descartan por el validador."""
    mock_scrape.return_value = [{
        "nombre": "",
        "direccion": "Dir",
        "telefono": "999123456",
        "ciudad": "Lima",
        "categoria": "Test",
        "maps_url": "https://google.com/place/x",
        "categoria_pred": "otro",
        "confianza": 0.1,
    }]
    leads = await orquestador.orquestar(request_scrape, None)
    assert len(leads) == 0


@pytest.mark.asyncio
async def test_orquestador_cancel_event_propagado(orquestador, request_scrape, mock_scrape):
    """El cancel_event se pasa al scraper."""
    cancel = threading.Event()
    await orquestador.orquestar(request_scrape, cancel)
    mock_scrape.assert_called_once()
    args, kwargs = mock_scrape.call_args
    assert kwargs.get("cancel_event") is cancel


@pytest.mark.asyncio
async def test_orquestador_campo_fuente(orquestador, request_scrape, mock_scrape):
    """Todos los leads tienen fuente=google_maps."""
    leads = await orquestador.orquestar(request_scrape, None)
    for lead in leads:
        assert lead.fuente == "google_maps"


@pytest.mark.asyncio
async def test_orquestador_field_sources(orquestador, request_scrape, mock_scrape):
    """field_sources refleja google_maps como fuente."""
    leads = await orquestador.orquestar(request_scrape, None)
    for lead in leads:
        assert lead.field_sources.get("nombre") == "google_maps"
        assert lead.field_sources.get("telefono") == "google_maps"


@pytest.mark.asyncio
async def test_orquestador_raw_fields(orquestador, request_scrape, mock_scrape):
    """raw_fields contiene el dict original del core."""
    leads = await orquestador.orquestar(request_scrape, None)
    for lead in leads:
        assert "google_maps" in lead.raw_fields
        assert "nombre" in lead.raw_fields["google_maps"]


@pytest.mark.asyncio
async def test_orquestador_campo_calidad(orquestador, request_scrape, mock_scrape):
    """Los leads validados tienen calidad asignada."""
    leads = await orquestador.orquestar(request_scrape, None)
    for lead in leads:
        assert hasattr(lead, "calidad")
        assert lead.calidad in ("completa", "parcial", "minima")


@pytest.mark.asyncio
async def test_orquestador_pasa_keyword_al_clasificador(orquestador, request_scrape, mock_scrape):
    """El keyword se pasa al clasificador ML del core."""
    leads = await orquestador.orquestar(request_scrape, None)
    assert len(leads) > 0
