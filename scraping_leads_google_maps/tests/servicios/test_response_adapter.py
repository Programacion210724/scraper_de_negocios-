"""Tests del response_adapter: Lead[] -> formato legacy dict[].

Verifica que:
  - El rename categoria_busqueda -> categoria funciona
  - maps_url cae back a url_raw cuando maps_url es None
  - categoria_pred y confianza se preservan
  - La lista vacia produce []
  - Todos los campos esperados por el frontend estan presentes
"""
import pytest

from modelos.lead import Lead
from servicios.response_adapter import leads_a_dict_legacy


def _make_lead(**kwargs):
    defaults = {
        "nombre": "Café A",
        "direccion": "Av. Arequipa 123",
        "telefono": "+51999123456",
        "ciudad": "Lima",
        "categoria_busqueda": "Cafeterías",
        "url_raw": "https://maps.google.com/place/cafe-a",
        "fuente": "google_maps",
        "maps_url": "https://maps.google.com/place/cafe-a",
        "categoria_pred": "restaurante",
        "confianza": 0.95,
    }
    defaults.update(kwargs)
    return Lead(**defaults)


def test_leads_a_dict_legacy_lista_vacia():
    assert leads_a_dict_legacy([]) == []


def test_leads_a_dict_legacy_mapea_categoria_busqueda_a_categoria():
    lead = _make_lead(categoria_busqueda="Dentistas")
    result = leads_a_dict_legacy([lead])
    assert result[0]["categoria"] == "Dentistas"


def test_leads_a_dict_legacy_no_incluye_categoria_busqueda():
    """El formato legacy usa 'categoria', no 'categoria_busqueda'."""
    lead = _make_lead(categoria_busqueda="Test")
    result = leads_a_dict_legacy([lead])
    assert "categoria_busqueda" not in result[0]


def test_leads_a_dict_legacy_preserva_campos_requeridos():
    lead = _make_lead()
    result = leads_a_dict_legacy([lead])
    d = result[0]
    assert d["nombre"] == "Café A"
    assert d["direccion"] == "Av. Arequipa 123"
    assert d["telefono"] == "+51999123456"
    assert d["ciudad"] == "Lima"
    assert d["categoria"] == "Cafeterías"
    assert d["maps_url"] == "https://maps.google.com/place/cafe-a"
    assert d["categoria_pred"] == "restaurante"
    assert d["confianza"] == 0.95


def test_leads_a_dict_legacy_maps_url_fallback_a_url_raw():
    """Si maps_url es None, usa url_raw como fallback."""
    lead = _make_lead(maps_url=None, url_raw="https://maps.google.com/place/fallback")
    result = leads_a_dict_legacy([lead])
    assert result[0]["maps_url"] == "https://maps.google.com/place/fallback"


def test_leads_a_dict_legacy_maps_url_vacio_cuando_ambos_none():
    """Si maps_url y url_raw son None, maps_url es ''."""
    lead = _make_lead(maps_url=None, url_raw="")
    result = leads_a_dict_legacy([lead])
    assert result[0]["maps_url"] == ""


def test_leads_a_dict_legacy_categoria_pred_none():
    lead = _make_lead(categoria_pred=None, confianza=None)
    result = leads_a_dict_legacy([lead])
    assert result[0]["categoria_pred"] is None
    assert result[0]["confianza"] is None


def test_leads_a_dict_legacy_multiple_leads():
    leads = [
        _make_lead(nombre="Café A", categoria_busqueda="Cafeterías"),
        _make_lead(nombre="Clínica B", categoria_busqueda="Salud"),
    ]
    result = leads_a_dict_legacy(leads)
    assert len(result) == 2
    assert result[0]["nombre"] == "Café A"
    assert result[0]["categoria"] == "Cafeterías"
    assert result[1]["nombre"] == "Clínica B"
    assert result[1]["categoria"] == "Salud"


def test_leads_a_dict_legacy_tiene_exactamente_8_claves():
    """El formato legacy debe tener exactamente las 8 claves esperadas."""
    lead = _make_lead()
    result = leads_a_dict_legacy([lead])
    d = result[0]
    expected_keys = {
        "nombre", "direccion", "telefono", "ciudad",
        "categoria", "maps_url", "categoria_pred", "confianza",
    }
    assert set(d.keys()) == expected_keys
