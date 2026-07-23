import pytest
from app import app as flask_app

@pytest.fixture
def app():
    flask_app.config.update({
        "TESTING": True,
    })
    yield flask_app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def sample_results():
    return [
        {
            "nombre": "Clínica Dental Madrid",
            "direccion": "Calle Mayor 10, Madrid",
            "telefono": "+34 912 345 678",
            "ciudad": "Madrid",
            "categoria": "Dentistas",
            "maps_url": "https://maps.google.com/place/abc123"
        },
        {
            "nombre": "Dentistas López",
            "direccion": "Av. de la Constitución 25, Madrid",
            "telefono": "+34 911 234 567",
            "ciudad": "Madrid",
            "categoria": "Dentistas",
            "maps_url": "https://maps.google.com/place/def456"
        }
    ]
