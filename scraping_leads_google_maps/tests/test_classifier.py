"""Tests del filtrado y agrupación del modelo ML.

Verifican que `filter_and_group`:
- no recorta el número de registros por debajo del input (los ruidosos se
  reincorporan al final), y
- agrega los campos `categoria_pred` y `confianza` a cada registro.
"""
from scraper.classifier import LeadClassifier, _NaiveClassifier


def _naive_classifier() -> LeadClassifier:
    """Clasificador en modo naive (sin sklearn) para tests deterministas."""
    clf = LeadClassifier()
    clf._pipeline = None
    clf._naive = _NaiveClassifier()
    clf._loaded = True
    return clf


def _valid(nombre, telefono="+34 912 345 678", direccion="Calle Mayor 10", maps_url="https://maps.google.com/place/x"):
    return {
        "nombre": nombre,
        "direccion": direccion,
        "telefono": telefono,
        "ciudad": "Madrid",
        "categoria": "Dentistas",
        "maps_url": maps_url,
    }


def _noise_empty_name():
    return _valid("Sin nombre")


def _noise_no_data():
    return {"nombre": "X", "direccion": "", "telefono": "", "ciudad": "Madrid", "categoria": "Y", "maps_url": ""}


def test_filter_and_group_preserves_count_with_noise():
    clf = _naive_classifier()
    items = [_valid("Clínica Dental Madrid"), _noise_empty_name(), _noise_no_data(), _valid("Dentistas López")]
    out = clf.filter_and_group(items, keyword="Dentistas")
    assert len(out) == len(items), "El filtrado ML no debe recortar el número de registros"


def test_filter_and_group_appends_noise_at_end():
    clf = _naive_classifier()
    items = [_valid("Clínica Dental Madrid"), _noise_empty_name()]
    out = clf.filter_and_group(items, keyword="Dentistas")
    assert len(out) == 2
    # El ruidoso se reincorpora con categoria_pred 'otro' y baja confianza
    assert out[-1]["categoria_pred"] == "otro"
    assert out[-1]["confianza"] == 0.0
    assert out[-1]["nombre"] == "Sin nombre"


def test_filter_and_group_adds_ml_fields():
    clf = _naive_classifier()
    items = [_valid("Clínica Dental Madrid")]
    out = clf.filter_and_group(items, keyword="Dentistas")
    assert len(out) == 1
    assert "categoria_pred" in out[0]
    assert "confianza" in out[0]


def test_filter_and_group_preserves_fields():
    clf = _naive_classifier()
    items = [_valid("Clínica Dental Madrid", telefono="+34 912 345 678")]
    out = clf.filter_and_group(items, keyword="Dentistas")
    assert len(out) == 1
    for field in ("nombre", "direccion", "telefono", "ciudad", "categoria", "maps_url"):
        assert field in out[0]


def test_filter_and_group_empty_input():
    clf = _naive_classifier()
    assert clf.filter_and_group([], keyword="Dentistas") == []
