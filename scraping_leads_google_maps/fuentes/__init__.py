"""Registro de fuentes de scraping V2.

Al importar este paquete, las fuentes se registran automaticamente
en el ScraperFactory. Nuevas fuentes: crear en fuentes/<nombre>.py,
importar y registrar aqui.
"""
from servicios.fabrica_scrapers import ScraperFactory
from fuentes.google_maps import GoogleMapsSource

# Registro automatica de Google Maps al importar el paquete
ScraperFactory.register(GoogleMapsSource())


def get_fuente(nombre: str):
    """Obtiene una fuente por nombre.

    Args:
        nombre: Identificador de la fuente (ej: 'google_maps').

    Returns:
        ScraperInterface: Instancia del scraper solicitado.
    """
    return ScraperFactory.get(nombre)


def listar_fuentes() -> list:
    """Lista los nombres de fuentes registradas."""
    return ScraperFactory.list_sources()
