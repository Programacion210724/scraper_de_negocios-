"""Tests del ClasificadorServicio (Option C: skip leads ya clasificados).

Verifica:
  - Todos los leads ya clasificados → skip completo, orden preservado
  - Ningun lead clasificado → clasificacion completa
  - Mezcla de clasificados y pendientes → solo clasificar pendientes
  - Clasificacion parcialmente incompleta (categoria_pred sin confianza, viceversa)
  - Preservacion del orden original
  - force=True reclasifica todos
"""
import pytest
from unittest.mock import AsyncMock, patch

from modelos.lead import Lead
from servicios.clasificador_servicio import ClasificadorServicio


@pytest.fixture
def clasificador():
    return ClasificadorServicio()


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


def _mocked_filter_and_group():
    """Factory que retornan dicts con categoria_pred y confianza simuladas."""
    def mock_fn(dicts, keyword=""):
        results = []
        for d in dicts:
            # Simular clasificacion ML
            nombre_lower = (d.get("nombre") or "").lower()
            if "cafe" in nombre_lower:
                cat, conf = "restaurante", 0.95
            elif "clinica" in nombre_lower or "dental" in nombre_lower:
                cat, conf = "salud", 0.90
            else:
                cat, conf = "otro", 0.30
            results.append({**d, "categoria_pred": cat, "confianza": round(conf, 3)})
        return results
    return mock_fn


# --- Todos los leads ya clasificados → skip ---

def test_skip_todos_clasificados(clasificador):
    """Si todos los leads tienen categoria_pred y confianza, se omite clasificacion."""
    leads = [
        _lead(nombre="Cafe A", categoria_pred="restaurante", confianza=0.95),
        _lead(nombre="Clinica B", categoria_pred="salud", confianza=0.90),
    ]
    with patch("servicios.clasificador_servicio._classifier.filter_and_group") as mock:
        result = clasificador.clasificar(leads, keyword="test")
        mock.assert_not_called()  # NO se llama al clasificador

    assert len(result) == 2
    assert result is leads  # Mismo orden, mismos objetos


def test_skip_preserva_valores_originales(clasificador):
    """Los valores originales de categoria_pred/confianza se conservan."""
    leads = [_lead(nombre="Cafe", categoria_pred="restaurante", confianza=0.95)]
    result = clasificador.clasificar(leads)
    assert result[0].categoria_pred == "restaurante"
    assert result[0].confianza == 0.95


def test_skip_preserva_orden(clasificador):
    """El orden original se preserva al hacer skip."""
    leads = [
        _lead(nombre="Zeta", categoria_pred="otro", confianza=0.1),
        _lead(nombre="Alpha", categoria_pred="restaurante", confianza=0.9),
        _lead(nombre="Beta", categoria_pred="servicio", confianza=0.5),
    ]
    result = clasificador.clasificar(leads)
    assert [l.nombre for l in result] == ["Zeta", "Alpha", "Beta"]


# --- Ningun lead clasificado → clasificacion completa ---

def test_clasificacion_completa_todos_pendientes(clasificador):
    """Si ningun lead tiene categoria_pred, clasifica todos."""
    leads = [
        _lead(nombre="Cafe Central"),
        _lead(nombre="Clinica Dental"),
    ]
    with patch("servicios.clasificador_servicio._classifier.filter_and_group",
               side_effect=_mocked_filter_and_group()):
        result = clasificador.clasificar(leads, keyword="test")

    assert len(result) == 2
    assert all(l.categoria_pred is not None for l in result)
    assert all(l.confianza is not None for l in result)
    assert result[0].categoria_pred == "restaurante"
    assert result[1].categoria_pred == "salud"


def test_lista_vacia(clasificador):
    assert clasificador.clasificar([]) == []


# --- Mezcla de clasificados y pendientes ---

def test_mezcla_solo_clasifica_pendientes(clasificador):
    """Solo los leads pendientes son clasificados; los clasificados se preservan."""
    lead_clasificado = _lead(nombre="Cafe A", categoria_pred="restaurante", confianza=0.95)
    lead_pendiente = _lead(nombre="Clinica B")  # categoria_pred=None

    with patch("servicios.clasificador_servicio._classifier.filter_and_group",
               side_effect=_mocked_filter_and_group()) as mock:
        result = clasificador.clasificar([lead_clasificado, lead_pendiente], keyword="test")
        # filter_and_group called ONCE, only with the pendiente
        assert mock.call_count == 1
        call_args = mock.call_args
        assert len(call_args[0][0]) == 1  # 1 dict (solo el pendiente)
        assert call_args[0][0][0]["nombre"] == "Clinica B"

    assert result[0].categoria_pred == "restaurante"  # preservado
    assert result[0].confianza == 0.95               # preservado
    assert result[1].categoria_pred == "salud"        # clasificado
    assert result[1].confianza == 0.9                  # clasificado


def test_mezcla_preserva_orden(clasificador):
    """El orden original se preserva en mezclas clasificado/pendiente."""
    lead1 = _lead(nombre="Cafe A", categoria_pred="restaurante", confianza=0.95)
    lead2 = _lead(nombre="Clinica B")  # pendiente
    lead3 = _lead(nombre="Cafe C", categoria_pred="restaurante", confianza=0.88)

    with patch("servicios.clasificador_servicio._classifier.filter_and_group",
               side_effect=_mocked_filter_and_group()):
        result = clasificador.clasificar([lead1, lead2, lead3], keyword="test")

    assert [l.nombre for l in result] == ["Cafe A", "Clinica B", "Cafe C"]


# --- Clasificacion parcialmente incompleta ---

def test_categoria_pred_sin_confianza_es_pendiente(clasificador):
    """Lead con categoria_pred pero confianza=None → pendiente."""
    lead = _lead(nombre="Cafe A", categoria_pred="restaurante", confianza=None)
    with patch("servicios.clasificador_servicio._classifier.filter_and_group",
               side_effect=_mocked_filter_and_group()):
        result = clasificador.clasificar([lead], keyword="test")
    assert result[0].confianza is not None
    assert result[0].categoria_pred is not None


def test_confianza_sin_categoria_pred_es_pendiente(clasificador):
    """Lead con confianza pero categoria_pred=None → pendiente."""
    lead = _lead(nombre="Cafe A", categoria_pred=None, confianza=0.95)
    with patch("servicios.clasificador_servicio._classifier.filter_and_group",
               side_effect=_mocked_filter_and_group()):
        result = clasificador.clasificar([lead], keyword="test")
    assert result[0].categoria_pred is not None
    assert result[0].confianza is not None


def test_both_none_es_pendiente(clasificador):
    """Lead con categoria_pred=None y confianza=None → pendiente."""
    lead = _lead(nombre="Cafe A", categoria_pred=None, confianza=None)
    with patch("servicios.clasificador_servicio._classifier.filter_and_group",
               side_effect=_mocked_filter_and_group()):
        result = clasificador.clasificar([lead], keyword="test")
    assert result[0].categoria_pred is not None
    assert result[0].confianza is not None


# --- force=True ---

def test_force_reclasifica_todos(clasificador):
    """force=True reclasifica incluso leads ya clasificados."""
    lead = _lead(nombre="Clinica B", categoria_pred="restaurante", confianza=0.95)
    with patch("servicios.clasificador_servicio._classifier.filter_and_group",
               side_effect=_mocked_filter_and_group()) as mock:
        result = clasificador.clasificar([lead], keyword="test", force=True)
        mock.assert_called_once()

    # Reclasificado con datos normalizados → puede diferir del original
    assert result[0].categoria_pred == "salud"  # "Clinica B" contiene "clinica"
    assert result[0].confianza == 0.9


def test_force_preserve_order(clasificador):
    """force=True preserva el orden original tras reclasificar."""
    leads = [
        _lead(nombre="Cafe A", categoria_pred="restaurante", confianza=0.95),
        _lead(nombre="Clinica B", categoria_pred="otro", confianza=0.30),
    ]
    with patch("servicios.clasificador_servicio._classifier.filter_and_group",
               side_effect=_mocked_filter_and_group()):
        result = clasificador.clasificar(leads, keyword="test", force=True)
    assert [l.nombre for l in result] == ["Cafe A", "Clinica B"]
