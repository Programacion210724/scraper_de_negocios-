"""Tests del registro de fuentes (ScraperFactory registry).

Verifica que al importar `fuentes`, GoogleMapsSource se registra
correctamente en el ScraperFactory, evitando el ValueError que ocurria
cuando el registry estaba vacio.
"""
import pytest

import fuentes  # noqa: F401 — import activa el registro
from servicios.fabrica_scrapers import ScraperFactory


def test_registry_tiene_google_maps():
    """GoogleMapsSource debe estar registrada como 'google_maps'."""
    assert "google_maps" in ScraperFactory.list_sources()


def test_registry_get_google_maps_devuelve_source():
    """ScraperFactory.get('google_maps') devuelve la instancia registrada."""
    source = ScraperFactory.get("google_maps")
    assert source is not None
    assert source.source_name == "google_maps"


def test_registry_get_fuente_desconocida_raises():
    """ScraperFactory.get con fuente inexistente levanta ValueError."""
    with pytest.raises(ValueError, match="Fuente desconocida"):
        ScraperFactory.get("fuente_inexistente")
