"""Tests del normalizador de leads.

Verifica:
  - normalizar_telefono: formato E.164 para Peru (+51)
  - normalizar_nombre: lowercase, strip acentos, quitar S.A.C./S.A.
  - normalizar_direccion: normaliza abreviaturas
  - normalizar_url: usa _normalizar_maps_url del core para google_maps
  - normalizar_lead: aplica todas las normalizaciones
"""
import pytest

from modelos.lead import Lead
from servicios.normalizador import Normalizador


@pytest.fixture
def normalizador():
    return Normalizador()


# --- normalizar_telefono ---

def test_normalizar_telefono_movil_peru(normalizador):
    assert normalizador.normalizar_telefono("999123456") == "+51999123456"


def test_normalizar_telefono_fijo_lima(normalizador):
    assert normalizador.normalizar_telefono("01-1234567") == "+5111234567"


def test_normalizar_telefono_con_guiones(normalizador):
    assert normalizador.normalizar_telefono("999-123-456") == "+51999123456"


def test_normalizar_telefono_internacional_con_espacios(normalizador):
    assert normalizador.normalizar_telefono("+51 999 123 456") == "+51999123456"


def test_normalizar_telefono_con_espacios(normalizador):
    assert normalizador.normalizar_telefono("999 123 456") == "+51999123456"


def test_normalizar_telefono_muy_corto(normalizador):
    assert normalizador.normalizar_telefono("123") == ""


def test_normalizar_telefono_vacio(normalizador):
    assert normalizador.normalizar_telefono("") == ""
    assert normalizador.normalizar_telefono(None) == ""


def test_normalizar_telefono_fijo_8_digitos_con_cero(normalizador):
    """Fijo de 8 digitos con 0 inicial: 021234567 -> +5121234567"""
    assert normalizador.normalizar_telefono("021234567") == "+5121234567"


# --- normalizar_nombre ---

def test_normalizar_nombre_quita_acentos(normalizador):
    assert normalizador.normalizar_nombre("Ferretería") == "ferreteria"


def test_normalizar_nombre_quita_sufijo_sac(normalizador):
    result = normalizador.normalizar_nombre("Ferretería El Constructor S.A.C.")
    assert "s.a.c" not in result
    assert result == "ferreteria el constructor"


def test_normalizar_nombre_quita_sufijo_sa(normalizador):
    result = normalizador.normalizar_nombre("Café Madrid S.A.")
    assert "s.a" not in result
    assert result == "cafe madrid"


def test_normalizar_nombre_quita_sufijo_srl(normalizador):
    result = normalizador.normalizar_nombre("Inversiones ABC S.R.L.")
    assert "s.r.l" not in result
    assert result == "inversiones abc"


def test_normalizar_nombre_lower(normalizador):
    result = normalizador.normalizar_nombre("CAFE DEL BUEN SABOR")
    assert result == "cafe del buen sabor"


def test_normalizar_nombre_vacio(normalizador):
    assert normalizador.normalizar_nombre("") == ""
    assert normalizador.normalizar_nombre(None) == ""


def test_normalizar_nombre_sin_sufijo(normalizador):
    assert normalizador.normalizar_nombre("Panaderia El Buen Pan") == "panaderia el buen pan"


# --- normalizar_direccion ---

def test_normalizar_direccion_abreviaturas(normalizador):
    assert normalizador.normalizar_direccion("Av. Arequipa 123") == "av arequipa 123"


def test_normalizar_direccion_avenida_completa(normalizador):
    assert normalizador.normalizar_direccion("Avenida Arequipa 123") == "av arequipa 123"


def test_normalizar_direccion_calle(normalizador):
    assert normalizador.normalizar_direccion("Calle Mayor 10") == "calle mayor 10"


def test_normalizar_direccion_vacia(normalizador):
    assert normalizador.normalizar_direccion("") == ""
    assert normalizador.normalizar_direccion(None) == ""


# --- normalizar_url ---

def test_normalizar_url_google_maps_reutiliza_core(normalizador):
    """normalizar_url para google_maps delega al core _normalizar_maps_url."""
    from scraper.scraper import _normalizar_maps_url
    url = "https://www.google.com/maps/place/Test/@1.2,3.4,15z/data=!3m1!4b1?foo=bar#frag"
    result = normalizador.normalizar_url(url, "google_maps")
    assert result == _normalizar_maps_url(url)
    assert "@1.2,3.4" not in result
    assert "?foo=bar" not in result
    assert "Test/" in result


def test_normalizar_url_google_maps_place_slug(normalizador):
    url = "https://maps.google.com/place/Café+A+/"
    result = normalizador.normalizar_url(url, "google_maps")
    assert "place/" in result


def test_normalizar_url_fuente_desconocida(normalizador):
    url = "https://example.com/path?foo=bar#frag"
    result = normalizador.normalizar_url(url, "desconocida")
    assert "?" not in result
    assert "#" not in result
    assert result == "https://example.com/path"


def test_normalizar_url_vacio(normalizador):
    assert normalizador.normalizar_url("", "google_maps") == ""


# --- normalizar_lead ---

def test_normalizar_lead_aplica_todas_las_normalizaciones(normalizador):
    lead = Lead(
        nombre="Ferretería El Constructor S.A.C.",
        direccion="Av. Arequipa 123",
        telefono="999-123-456",
        ciudad="Lima",
        categoria_busqueda="Ferretería",
        url_raw="https://maps.google.com/place/ferreteria",
        fuente="google_maps",
        maps_url="https://maps.google.com/place/ferreteria",
    )
    result = normalizador.normalizar_lead(lead)
    # Telefono normalizado
    assert result.telefono == "+51999123456"
    # Nombre normalizado almacenado en nombre_norm
    assert result.nombre_norm == "ferreteria el constructor"
    # Direccion normalizada
    assert result.direccion == "av arequipa 123"
    # URLs normalizadas
    assert "ferreteria" in result.url_raw
    assert "ferreteria" in result.maps_url


def test_normalizar_lead_preserva_campos_no_normalizables(normalizador):
    lead = Lead(
        nombre="Test",
        direccion="",
        telefono="invalid",
        ciudad="Lima",
        categoria_busqueda="Test",
        url_raw="",
        fuente="google_maps",
    )
    result = normalizador.normalizar_lead(lead)
    assert result.nombre == "Test"  # nombre no cambia (solo nombre_norm)
    assert result.direccion == ""  # direccion vacia no cambia
    assert result.telefono == ""  # telefono invalido -> ""
    assert result.ciudad == "Lima"  # ciudad no se normaliza
