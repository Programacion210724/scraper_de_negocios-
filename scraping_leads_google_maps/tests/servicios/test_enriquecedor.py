"""Tests del enriquecedor cross-source.

Verifica:
  - Single source: passthrough (lead sin cambios)
  - Cross-source merge: field-by-field complement, field_sources tracking
  - _merge_grupo: sort por priority + confianza, merge conservativo
"""
import pytest

from modelos.lead import Lead
from servicios.enriquecedor import Enriquecedor


@pytest.fixture
def enriquecedor():
    return Enriquecedor()


def _lead(**kwargs):
    """Crea un Lead con field_sources basicos de google_maps por defecto."""
    defaults = {
        "nombre": "Test",
        "direccion": "Calle 1",
        "telefono": "+51999123456",
        "ciudad": "Lima",
        "categoria_busqueda": "Test",
        "url_raw": "https://maps.google.com/place/test",
        "fuente": "google_maps",
        "field_sources": {"nombre": "google_maps", "telefono": "google_maps",
                          "direccion": "google_maps", "ciudad": "google_maps"},
    }
    defaults.update(kwargs)
    return Lead(**defaults)


def test_enriquecer_lista_vacia(enriquecedor):
    assert enriquecedor.enriquecer([]) == []


def test_enriquecer_single_source_passthrough(enriquecedor):
    """Con una sola fuente, cada grupo tiene 1 lead -> leads sin cambios."""
    leads = [_lead(nombre=f"Cafe {i}", telefono=f"99912345{i}") for i in range(3)]
    result = enriquecedor.enriquecer(leads)
    assert len(result) == 3
    # Los objs son los mismos (passthrough no copia)
    assert all(r is l for r, l in zip(result, leads))


def test_enriquecer_single_source_preserva_fields(enriquecedor):
    lead = _lead(
        nombre="Cafe A",
        telefono="999123456",
        direccion="Av. Arequipa 123",
        url_raw="https://maps.google.com/place/a",
        categoria_pred="restaurante",
        confianza=0.95,
    )
    result = enriquecedor.enriquecer([lead])
    assert len(result) == 1
    assert result[0].nombre == "Cafe A"
    assert result[0].telefono == "999123456"
    assert result[0].categoria_pred == "restaurante"
    assert result[0].confianza == 0.95


def test_enriquecer_merge_complementa_email(enriquecedor, monkeypatch):
    """Lead de google_maps sin email + Lead de deperu con email -> merge."""
    monkeypatch.setattr(
        enriquecedor, "_get_priority",
        lambda l: 10 if l.fuente == "google_maps" else 8,
    )
    lead_gm = _lead(
        nombre="Cafe A",
        telefono="999123456",
        email=None,
        fuente="google_maps",
        categoria_pred="restaurante",
        confianza=0.95,
    )
    lead_dp = _lead(
        nombre="Cafe A",
        telefono="999123456",
        email="info@cafe.com",
        fuente="deperu",
        categoria_pred="restaurante",
        confianza=0.88,
        field_sources={"nombre": "deperu", "telefono": "deperu"},
    )
    result = enriquecedor.enriquecer([lead_gm, lead_dp])
    assert len(result) == 1
    merged = result[0]
    # Email complementado de deperu
    assert merged.email == "info@cafe.com"
    assert merged.field_sources["email"] == "deperu"
    # Telefono conservado de google_maps (priority 10, es la base)
    assert merged.field_sources["telefono"] == "google_maps"


def test_enriquecer_merge_no_sobrescribe(enriquecedor, monkeypatch):
    """El enriquecimiento complementa, nunca sobrescribe."""
    monkeypatch.setattr(
        enriquecedor, "_get_priority",
        lambda l: 10 if l.fuente == "google_maps" else 8,
    )
    lead_gm = _lead(nombre="Cafe A", telefono="999123456", direccion="Av. Arequipa 1", fuente="google_maps")
    lead_dp = _lead(nombre="Cafe A", telefono="999123456", direccion="Calle 2", fuente="deperu",
                    field_sources={"nombre": "deperu", "telefono": "deperu", "direccion": "deperu"})
    result = enriquecedor.enriquecer([lead_gm, lead_dp])
    assert len(result) == 1
    # direccion de google_maps (priority 10) se conserva
    assert result[0].direccion == "Av. Arequipa 1"


def test_enriquecer_merge_consolida_raw_fields(enriquecedor, monkeypatch):
    monkeypatch.setattr(
        enriquecedor, "_get_priority",
        lambda l: 10 if l.fuente == "google_maps" else 8,
    )
    lead_gm = _lead(nombre="Cafe A", telefono="999123456", fuente="google_maps")
    lead_gm.raw_fields["google_maps"] = {"business_id": "abc"}
    lead_dp = _lead(nombre="Cafe A", telefono="999123456", fuente="deperu",
                    field_sources={"nombre": "deperu", "telefono": "deperu"})
    lead_dp.raw_fields["deperu"] = {"ruc": "20123456789"}
    result = enriquecedor.enriquecer([lead_gm, lead_dp])
    assert len(result) == 1
    assert "google_maps" in result[0].raw_fields
    assert "deperu" in result[0].raw_fields
    assert result[0].raw_fields["deperu"]["ruc"] == "20123456789"


def test_enriquecer_merge_sort_por_priority(enriquecedor, monkeypatch):
    """Lead con mayor priority va primero (es la base)."""
    monkeypatch.setattr(
        enriquecedor, "_get_priority",
        lambda l: 10 if l.fuente == "google_maps" else 8,
    )
    lead_dp = _lead(nombre="Cafe A", telefono="999123456", email=None, fuente="deperu",
                    field_sources={"nombre": "deperu", "telefono": "deperu"})
    lead_gm = _lead(nombre="Cafe A", telefono="999123456", email="gm@cafe.com", fuente="google_maps", field_sources={"nombre": "google_maps", "telefono": "google_maps", "direccion": "google_maps", "ciudad": "google_maps", "email": "google_maps"})
    result = enriquecedor.enriquecer([lead_dp, lead_gm])
    assert result[0].email == "gm@cafe.com"
    # email fue del base (google_maps) desde el inicio
    assert result[0].field_sources["email"] == "google_maps"

