"""Tests del modelo Lead unificado.

Verifican creacion, serializacion to_dict/from_dict y compatibilidad
con el formato de salida del core.
"""
from datetime import datetime

from modelos.lead import Lead


def test_lead_creacion_con_campos_requeridos():
    """Lead se puede crear con solo los campos requeridos."""
    lead = Lead(
        nombre="Café A",
        direccion="Av. Arequipa 123",
        telefono="+51 999 123 456",
        ciudad="Lima",
        categoria_busqueda="Cafeterías",
        url_raw="https://maps.google.com/place/cafe-a",
        fuente="google_maps",
    )
    assert lead.nombre == "Café A"
    assert lead.direccion == "Av. Arequipa 123"
    assert lead.telefono == "+51 999 123 456"
    assert lead.ciudad == "Lima"
    assert lead.categoria_busqueda == "Cafeterías"
    assert lead.url_raw == "https://maps.google.com/place/cafe-a"
    assert lead.fuente == "google_maps"


def test_lead_campos_opcionales_por_defecto():
    """Los campos opcionales toman valor None o vacio por defecto."""
    lead = Lead(
        nombre="Test",
        direccion="Dir",
        telefono="",
        ciudad="Lima",
        categoria_busqueda="Test",
        url_raw="https://example.com",
        fuente="google_maps",
    )
    assert lead.email is None
    assert lead.website is None
    assert lead.distrito is None
    assert lead.provincia is None
    assert lead.region is None
    assert lead.categoria_fuente is None
    assert lead.maps_url is None
    assert lead.latitud is None
    assert lead.longitud is None
    assert lead.rating is None
    assert lead.reviews_count is None
    assert lead.precio is None
    assert lead.categoria_pred is None
    assert lead.confianza is None
    assert lead.raw_fields == {}
    assert lead.field_sources == {}
    assert lead.job_id == ""


def test_lead_to_dict_contiene_todos_los_campos():
    """to_dict serializa todos los campos del modelo."""
    lead = Lead(
        nombre="Café A",
        direccion="Av. Arequipa 123",
        telefono="+51 999 123 456",
        ciudad="Lima",
        categoria_busqueda="Cafeterías",
        url_raw="https://maps.google.com/place/cafe-a",
        fuente="google_maps",
    )
    d = lead.to_dict()
    # Campos requeridos
    assert d["nombre"] == "Café A"
    assert d["direccion"] == "Av. Arequipa 123"
    assert d["telefono"] == "+51 999 123 456"
    assert d["ciudad"] == "Lima"
    assert d["categoria_busqueda"] == "Cafeterías"
    assert d["url_raw"] == "https://maps.google.com/place/cafe-a"
    assert d["fuente"] == "google_maps"
    # Campos opcionales
    assert d["email"] is None
    assert d["maps_url"] is None
    assert d["categoria_pred"] is None
    assert d["confianza"] is None
    assert d["raw_fields"] == {}
    assert d["field_sources"] == {}


def test_lead_to_dict_serializa_scraped_at_como_iso():
    """scraped_at se serializa como string ISO para JSON."""
    lead = Lead(
        nombre="Test",
        direccion="Dir",
        telefono="",
        ciudad="Lima",
        categoria_busqueda="Test",
        url_raw="https://example.com",
        fuente="google_maps",
    )
    d = lead.to_dict()
    assert "scraped_at" in d
    assert isinstance(d["scraped_at"], str)
    # Verificar que es un datetime ISO valido
    datetime.fromisoformat(d["scraped_at"])


def test_lead_from_dict_crea_instancia_correctamente():
    """from_dict deserializa correctamente todos los campos."""
    data = {
        "nombre": "Café A",
        "direccion": "Av. Arequipa 123",
        "telefono": "+51 999 123 456",
        "ciudad": "Lima",
        "categoria_busqueda": "Cafeterías",
        "url_raw": "https://maps.google.com/place/cafe-a",
        "fuente": "google_maps",
        "email": "info@cafe.com",
        "website": "https://cafe.com",
        "categoria_pred": "restaurante",
        "confianza": 0.95,
        "raw_fields": {"google_maps": {"business_id": "abc123"}},
        "field_sources": {"telefono": "google_maps"},
        "scraped_at": "2026-08-30T12:00:00",
        "job_id": "job-123",
    }
    lead = Lead.from_dict(data)
    assert lead.nombre == "Café A"
    assert lead.email == "info@cafe.com"
    assert lead.website == "https://cafe.com"
    assert lead.categoria_pred == "restaurante"
    assert lead.confianza == 0.95
    assert lead.raw_fields == {"google_maps": {"business_id": "abc123"}}
    assert lead.field_sources == {"telefono": "google_maps"}
    assert lead.job_id == "job-123"
    # scraped_at como string ISO -> datetime
    assert lead.scraped_at == datetime(2026, 8, 30, 12, 0, 0)


def test_lead_from_dict_con_datetime_scraped_at():
    """from_dict acepta scraped_at como objeto datetime directamente."""
    dt = datetime(2026, 1, 15, 8, 30, 0)
    lead = Lead.from_dict({
        "nombre": "Test",
        "direccion": "Dir",
        "telefono": "",
        "ciudad": "Lima",
        "categoria_busqueda": "Test",
        "url_raw": "https://example.com",
        "fuente": "google_maps",
        "scraped_at": dt,
    })
    assert lead.scraped_at == dt


def test_lead_roundtrip_to_dict_from_dict():
    """to_dict -> from_dict preserva todos los campos."""
    lead = Lead(
        nombre="Test Lead",
        direccion="Calle 123",
        telefono="+51999123456",
        ciudad="Lima",
        categoria_busqueda="Reparaciones",
        url_raw="https://maps.google.com/place/test",
        fuente="google_maps",
        email="test@example.com",
        website="https://test.com",
        categoria_pred="servicio",
        confianza=0.85,
        raw_fields={"google_maps": {"id": "xyz"}},
        field_sources={"telefono": "google_maps", "email": "deperu"},
        job_id="job-abc",
    )
    d = lead.to_dict()
    lead2 = Lead.from_dict(d)
    assert lead2.nombre == lead.nombre
    assert lead2.direccion == lead.direccion
    assert lead2.telefono == lead.telefono
    assert lead2.email == lead.email
    assert lead2.website == lead.website
    assert lead2.categoria_pred == lead.categoria_pred
    assert lead2.confianza == lead.confianza
    assert lead2.raw_fields == lead.raw_fields
    assert lead2.field_sources == lead.field_sources
    assert lead2.job_id == lead.job_id


def test_lead_from_dict_campos_faltantes_usan_defaults():
    """from_dict con datos parciales usa valores por defecto."""
    lead = Lead.from_dict({
        "nombre": "Test",
        "direccion": "",
        "telefono": "",
        "ciudad": "",
        "categoria_busqueda": "",
        "url_raw": "",
        "fuente": "google_maps",
    })
    assert lead.nombre == "Test"
    assert lead.email is None
    assert lead.categoria_pred is None
    assert lead.confianza is None
    assert lead.job_id == ""
    assert lead.raw_fields == {}
    assert lead.field_sources == {}


def test_lead_common_fields_incluye_campos_clave():
    """COMMON_FIELDS contiene los campos comunes del negocio."""
    assert "nombre" in Lead.COMMON_FIELDS
    assert "direccion" in Lead.COMMON_FIELDS
    assert "telefono" in Lead.COMMON_FIELDS
    assert "ciudad" in Lead.COMMON_FIELDS
    assert "email" in Lead.COMMON_FIELDS
    assert "website" in Lead.COMMON_FIELDS
    assert "categoria_busqueda" in Lead.COMMON_FIELDS
    # url_raw no es un common field (es especifico de fuente)
    assert "url_raw" not in Lead.COMMON_FIELDS
    assert "fuente" not in Lead.COMMON_FIELDS
    # Campos internos V2 no son parte del contrato de negocio comun
    assert "nombre_norm" not in Lead.COMMON_FIELDS
    assert "calidad" not in Lead.COMMON_FIELDS


def test_lead_campos_internos_por_defecto_none():
    """nombre_norm y calidad son campos internos V2 con valor None por defecto."""
    lead = Lead(
        nombre="Test",
        direccion="Dir",
        telefono="",
        ciudad="Lima",
        categoria_busqueda="Test",
        url_raw="https://example.com",
        fuente="google_maps",
    )
    assert lead.nombre_norm is None
    assert lead.calidad is None


def test_lead_to_dict_incluye_campos_internos():
    """to_dict serializa nombre_norm y calidad para coherencia roundtrip."""
    lead = Lead(
        nombre="Test",
        direccion="Dir",
        telefono="999",
        ciudad="Lima",
        categoria_busqueda="Test",
        url_raw="https://example.com",
        fuente="google_maps",
        nombre_norm="test",
        calidad="completa",
    )
    d = lead.to_dict()
    assert d["nombre_norm"] == "test"
    assert d["calidad"] == "completa"


def test_lead_from_dict_restaura_campos_internos():
    """from_dict restaura nombre_norm/calidad si vienen presentes."""
    lead = Lead.from_dict({
        "nombre": "Test",
        "direccion": "Dir",
        "telefono": "999",
        "ciudad": "Lima",
        "categoria_busqueda": "Test",
        "url_raw": "https://example.com",
        "fuente": "google_maps",
        "nombre_norm": "test",
        "calidad": "completa",
    })
    assert lead.nombre_norm == "test"
    assert lead.calidad == "completa"


def test_lead_roundtrip_campos_internos():
    """to_dict -> from_dict preserva nombre_norm y calidad."""
    lead = Lead(
        nombre="Test",
        direccion="Dir",
        telefono="999",
        ciudad="Lima",
        categoria_busqueda="Test",
        url_raw="https://example.com",
        fuente="google_maps",
        nombre_norm="test",
        calidad="parcial",
    )
    lead2 = Lead.from_dict(lead.to_dict())
    assert lead2.nombre_norm == "test"
    assert lead2.calidad == "parcial"
