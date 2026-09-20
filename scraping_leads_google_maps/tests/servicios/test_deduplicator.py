"""Tests del deduplicador multi-source.

Verifica:
  - calcular_dedup_key: prioridad coords -> phone -> name+city -> url -> hash
  - dedup_L1: intra-scrape (in-memory set)
  - dedup_L2: stub (sin BD, retorna leads sin cambios)
  - dedup_L3: no-op con single source, fuzzy con multiplres (simulado)
  - puntuacion_coincidencia: ponderaciones telefono/nombre/direccion/website/coords
"""
import pytest

from modelos.lead import Lead
from servicios.deduplicator import Deduplicator
from servicios.normalizador import Normalizador


@pytest.fixture
def normalizador():
    return Normalizador()


@pytest.fixture
def deduplicator(normalizador):
    return Deduplicator(normalizador)


def _lead(**kwargs):
    """Crea un Lead con campos por defecto."""
    defaults = {
        "nombre": "Test",
        "direccion": "Calle 1",
        "telefono": "+51999123456",
        "ciudad": "Lima",
        "categoria_busqueda": "Test",
        "url_raw": "https://maps.google.com/place/test",
        "fuente": "google_maps",
    }
    defaults.update(kwargs)
    return Lead(**defaults)


# --- calcular_dedup_key ---

def test_dedup_key_prioriza_coords(deduplicator):
    lead = _lead(latitud=-12.04, longitud=-77.03)
    key = deduplicator.calcular_dedup_key(lead)
    assert key.startswith("coords:")


def test_dedup_key_phone_tiene_prioridad_sobre_coords_vacio(deduplicator):
    lead = _lead(latitud=None, longitud=None, telefono="999123456")
    key = deduplicator.calcular_dedup_key(lead)
    assert key.startswith("phone:+51")


def test_dedup_key_prioriza_phone(deduplicator):
    lead = _lead(telefono="999123456")
    key = deduplicator.calcular_dedup_key(lead)
    assert key == "phone:+51999123456"


def test_dedup_key_normaliza_phone_para_key(deduplicator):
    """Telefonos con distinto formato pero mismo numero -> misma key."""
    lead1 = _lead(telefono="999-123-456")
    lead2 = _lead(telefono="+51 999 123 456")
    assert deduplicator.calcular_dedup_key(lead1) == deduplicator.calcular_dedup_key(lead2)


def test_dedup_key_name_ciudad_cuando_no_phone(deduplicator):
    lead = _lead(telefono="", nombre="Cafe A", ciudad="Lima")
    key = deduplicator.calcular_dedup_key(lead)
    assert key.startswith("name:")
    assert "cafe a" in key
    assert "lima" in key


def test_dedup_key_url_cuando_no_phone_ni_name(deduplicator):
    lead = _lead(
        telefono="",
        nombre="",
        ciudad="",
        url_raw="https://maps.google.com/place/cafe-a",
    )
    key = deduplicator.calcular_dedup_key(lead)
    assert key.startswith("url:")


def test_dedup_key_hash_fallback(deduplicator):
    """Lead con todos los campos vacios -> hash."""
    lead = _lead(
        telefono="",
        nombre="",
        ciudad="",
        url_raw="",
        maps_url="",
    )
    key = deduplicator.calcular_dedup_key(lead)
    assert key.startswith("hash:")


def test_dedup_key_same_data_different_name(deduplicator):
    lead1 = _lead(nombre="Cafe A", telefono="999123456")
    lead2 = _lead(nombre="Cafe B", telefono="999123456")
    assert deduplicator.calcular_dedup_key(lead1) == deduplicator.calcular_dedup_key(lead2)


def test_dedup_key_different_phone_different_key(deduplicator):
    lead1 = _lead(telefono="999123456")
    lead2 = _lead(telefono="987654321")
    assert deduplicator.calcular_dedup_key(lead1) != deduplicator.calcular_dedup_key(lead2)


# --- dedup_L1 ---

def test_dedup_L1_descarta_duplicados(deduplicator):
    lead1 = _lead(nombre="Cafe A", telefono="999123456")
    lead2 = _lead(nombre="Cafe B", telefono="999123456")  # mismo phone
    lead3 = _lead(nombre="Cafe C", telefono="987654321")  # phone distinto
    result = deduplicator.dedup_L1([lead1, lead2, lead3])
    assert len(result) == 2


def test_dedup_L1_mantiene_unico_si_no_duplicados(deduplicator):
    leads = [_lead(nombre=f"Cafe {i}", telefono=f"99912345{i}") for i in range(5)]
    result = deduplicator.dedup_L1(leads)
    assert len(result) == 5


def test_dedup_L1_lista_vacia(deduplicator):
    assert deduplicator.dedup_L1([]) == []


# --- dedup_L2 (stub) ---

def test_dedup_L2_stub_retorna_leads_sin_cambios(deduplicator):
    """En Fase 2 sin BD, dedup_L2 retorna leads sin cambios."""
    leads = [_lead(nombre=f"Cafe {i}") for i in range(3)]
    result = deduplicator.dedup_L2(leads, repository=None)
    assert result is leads


def test_dedup_L2_stub_preserva_cantidad(deduplicator):
    leads = [_lead(nombre=f"Cafe {i}") for i in range(5)]
    result = deduplicator.dedup_L2(leads, repository=None)
    assert len(result) == len(leads)


# --- dedup_L3 ---

def test_dedup_L3_no_op_single_source(deduplicator):
    """Con una sola fuente, L3 no hace nada."""
    leads = [_lead(nombre=f"Cafe {i}", telefono=f"99912345{i}") for i in range(3)]
    result = deduplicator.dedup_L3(leads)
    assert len(result) == 3


def test_dedup_L3_detecta_coincidencia_multi_source(deduplicator, monkeypatch):
    """Con 2 fuentes, L3 puede fundir leads con mismo dedup_key."""
    monkeypatch.setattr(
        deduplicator, "_get_priority",
        lambda l: 10 if l.fuente == "google_maps" else 8,
    )
    lead_a = _lead(nombre="Cafe A", telefono="999123456", fuente="google_maps")
    lead_b = _lead(nombre="Cafe A", telefono="999123456", fuente="deperu")
    result = deduplicator.dedup_L3([lead_a, lead_b])
    assert len(result) == 1


# --- puntuacion_coincidencia ---

def test_puntuacion_misma_identidad(deduplicator):
    """Mismo lead consigo mismo -> score 1.0."""
    lead = _lead(nombre="Cafe A", telefono="999123456", direccion="Av. Arequipa 123")
    score = deduplicator.puntuacion_coincidencia(lead, lead)
    assert score == pytest.approx(1.0)


def test_puntuacion_phone_match_alta(deduplicator):
    """Match exacto de telefono aporta 40%."""
    lead1 = _lead(nombre="A", telefono="999123456", direccion="Dir 1")
    lead2 = _lead(nombre="A", telefono="999123456", direccion="Dir 1")
    score = deduplicator.puntuacion_coincidencia(lead1, lead2)
    assert score > 0.8


def test_puntuacion_sin_campos_comunes(deduplicator):
    """Leads con campos vacios -> score 0.0."""
    lead1 = _lead(nombre="A", telefono="", direccion="")
    lead2 = _lead(nombre="B", telefono="", direccion="")
    score = deduplicator.puntuacion_coincidencia(lead1, lead2)
    assert score == 0.0


def test_puntuacion_nombre_fuzzy(deduplicator):
    """Nombres similares pero no iguales -> score intermedio."""
    lead1 = _lead(nombre="Cafe A", telefono="", direccion="")
    lead2 = _lead(nombre="Cafe B", telefono="", direccion="")
    score = deduplicator.puntuacion_coincidencia(lead1, lead2)
    assert 0 < score < 1
