import pytest
import re

from scraper.scraper import _dedup_key, _normalizar_maps_url


def clean_phone(aria_or_text: str) -> str:
    cleaned = re.sub(r'^(Teléfono|Phone|Llamar|Call):?\s*', '', aria_or_text).strip()
    return cleaned


def extract_phone_from_text(text: str) -> str:
    match = re.search(r'(\+\d{1,3}[\s.-]?\d{1,4}[\s.-]?\d{1,4}[\s.-]?\d{1,4}|(?<!\d)\d{3}[\s.-]?\d{3}[\s.-]?\d{3,4})', text)
    return match.group(1) if match else ""


def test_clean_phone_removes_prefix():
    assert clean_phone("Teléfono: +34 912 345 678") == "+34 912 345 678"


def test_clean_phone_removes_english_prefix():
    assert clean_phone("Phone: +1 555 123 4567") == "+1 555 123 4567"


def test_clean_phone_no_prefix():
    assert clean_phone("+34 912 345 678") == "+34 912 345 678"


def test_clean_phone_with_call_prefix():
    assert clean_phone("Llamar +34 912 345 678") == "+34 912 345 678"


def test_clean_phone_english_call():
    assert clean_phone("Call +1 555 123 4567") == "+1 555 123 4567"


def test_extract_phone_with_country_code():
    text = "Contacto: +34 912 345 678, email@test.com"
    assert extract_phone_from_text(text) == "+34 912 345 678"


def test_extract_phone_with_dashes():
    text = "Tel: 912-345-678"
    assert extract_phone_from_text(text) == "912-345-678"


def test_extract_phone_no_phone_in_text():
    assert extract_phone_from_text("No hay número aquí") == ""


def test_extract_phone_short_number_ignored():
    text = "Código: 123"
    assert extract_phone_from_text(text) == ""


# --- Modelo de datos ---
MANDATORY_FIELDS = {"nombre", "direccion", "telefono", "ciudad", "categoria", "maps_url"}


def test_result_has_all_required_fields():
    result = {
        "nombre": "Test",
        "direccion": "Calle 123",
        "telefono": "+34 912 345 678",
        "ciudad": "Madrid",
        "categoria": "Dentistas",
        "maps_url": "https://maps.google.com/place/test"
    }
    assert MANDATORY_FIELDS.issubset(result.keys())


def test_result_missing_field_fails():
    incomplete = {
        "nombre": "Test",
        "direccion": "Calle 123",
    }
    assert not MANDATORY_FIELDS.issubset(incomplete.keys())


def test_result_fields_are_strings():
    result = {
        "nombre": "Test",
        "direccion": "Calle 123",
        "telefono": "+34 912 345 678",
        "ciudad": "Madrid",
        "categoria": "Dentistas",
        "maps_url": "https://maps.google.com/place/test"
    }
    for field in MANDATORY_FIELDS:
        assert isinstance(result[field], str), f"{field} should be a string"


# --- Lógica de dirección ---
ADDRESS_KEYWORDS = ["calle", "av", "avenida", "jr", "rd"]


def extract_address(full_text: str) -> str:
    for line in full_text.split('\n'):
        line = line.strip()
        if any(kw.lower() in line.lower() for kw in ADDRESS_KEYWORDS):
            return line
    return ""


def test_extract_address_with_calle():
    text = "Clínica Dental Madrid\nCalle Mayor 10\nTeléfono: +34 912 345 678"
    assert "Calle Mayor 10" in extract_address(text)


def test_extract_address_with_av():
    text = "Dentistas López\nAv. de la Constitución 25\nTeléfono: +34 911 234 567"
    assert "Av. de la Constitución 25" in extract_address(text)


def test_extract_address_with_rd():
    text = "Best Pizza\n123 Main Rd\nPhone: +1 555 1234"
    result = extract_address(text)
    assert "123" in result
    assert "Main" in result
    assert "Rd" in result


def test_extract_address_not_found():
    text = "Solo un nombre\nSin dirección aquí"
    assert extract_address(text) == ""


# --- Deduplicación ---
def test_dedup_key_uses_maps_url():
    r1 = {"nombre": "Negocio A", "direccion": "Calle 1", "maps_url": "https://maps.google.com/place/a"}
    r2 = {"nombre": "Negocio B", "direccion": "Calle 2", "maps_url": "https://maps.google.com/place/a"}
    assert _dedup_key(r1) == _dedup_key(r2)


def test_dedup_key_normalizes_maps_url_tokens():
    """URLs distintas del mismo negocio (tokens/data/@coords) deben colisionar."""
    r1 = {"nombre": "Clínica Dental", "maps_url": "https://www.google.com/maps/place/Clínica+Dental/@37.1,-3.6,17z/data=!3m1!4bgsomething"}
    r2 = {"nombre": "Clínica Dental", "maps_url": "https://maps.google.com/place/Clínica+Dental/!1sabc123"}
    assert _dedup_key(r1) == _dedup_key(r2)


def test_dedup_key_differs_for_distinct_urls():
    r1 = {"nombre": "Negocio A", "maps_url": "https://maps.google.com/place/a"}
    r2 = {"nombre": "Negocio A", "maps_url": "https://maps.google.com/place/b"}
    assert _dedup_key(r1) != _dedup_key(r2)


def test_dedup_key_fallback_name_phone_address():
    r1 = {"nombre": "Negocio A", "direccion": "Calle 1", "telefono": "+34 912 345 678", "maps_url": ""}
    r2 = {"nombre": "Negocio A", "direccion": "Calle 1", "telefono": "+34 912 345 678", "maps_url": ""}
    assert _dedup_key(r1) == _dedup_key(r2)


def test_dedup_key_fallback_differs_by_phone():
    r1 = {"nombre": "Negocio A", "direccion": "Calle 1", "telefono": "+34 91 111 111", "maps_url": ""}
    r2 = {"nombre": "Negocio A", "direccion": "Calle 1", "telefono": "+34 91 222 222", "maps_url": ""}
    assert _dedup_key(r1) != _dedup_key(r2)


def test_dedup_key_fallback_distinct_address():
    r1 = {"nombre": "Negocio A", "direccion": "Calle 1", "telefono": "+34 912 345 678", "maps_url": ""}
    r2 = {"nombre": "Negocio A", "direccion": "Calle 2", "telefono": "+34 912 345 678", "maps_url": ""}
    assert _dedup_key(r1) != _dedup_key(r2)


def test_dedup_key_empty_url_uses_fallback():
    r1 = {"nombre": "Negocio A", "direccion": "Calle 1", "telefono": "+34 912 345 678", "maps_url": ""}
    assert _dedup_key(r1) != "url:"


def test_normalizar_maps_url_strips_params_and_coords():
    url = "https://www.google.com/maps/place/Test/@1.2,3.4,15z/data=!3m1!4b1?foo=bar#frag"
    norm = _normalizar_maps_url(url)
    assert "@1.2,3.4" not in norm
    assert "?foo=bar" not in norm
    assert "Test/" in norm


def test_dedup_key_prefers_url_over_fallback():
    r1 = {"nombre": "Negocio A", "direccion": "Calle 1", "maps_url": "https://maps.google.com/place/a"}
    r2 = {"nombre": "Negocio A", "direccion": "Calle 1", "maps_url": ""}
    assert _dedup_key(r1) != _dedup_key(r2)


def test_dedup_key_empty_maps_url_and_fields():
    r1 = {"maps_url": ""}
    assert _dedup_key(r1) == "name:|phone:|addr:"
