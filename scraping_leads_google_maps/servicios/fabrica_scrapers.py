"""Fabrica de scrapers — patron registry (factory).

Permite registrar e instanciar scrapers por nombre de fuente.
Las nuevas fuentes se agregan registrando una instancia en el factory,
sin modificar codigo existente (principio open/closed).
"""
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from fuentes.base import ScraperInterface
    from modelos.scrape_request import ScrapeRequest
    from modelos.lead import Lead

logger = logging.getLogger(__name__)


class ScraperFactory:
    """Registro e instancia de scrapers por fuente.

    Usa un dict de clase para almacenar scrapers registrados.
    Cada fuente se registra llamando a register() con una instancia
    de ScraperInterface.
    """

    _registry: dict = {}

    @classmethod
    def register(cls, scraper: "ScraperInterface") -> None:
        """Registra un scraper en el factory.

        Si ya existe una fuente con el mismo nombre, se sobrescribe
        con un warning.
        """
        if scraper.source_name in cls._registry:
            logger.warning(
                "Fuente '%s' ya registrada, sobrescribiendo", scraper.source_name
            )
        cls._registry[scraper.source_name] = scraper
        logger.info("Fuente '%s' registrada correctamente", scraper.source_name)

    @classmethod
    def get(cls, name: str) -> "ScraperInterface":
        """Obtiene un scraper por nombre.

        Raises:
            ValueError: Si la fuente no esta registrada.
        """
        if name not in cls._registry:
            disponibles = list(cls._registry.keys())
            raise ValueError(
                f"Fuente desconocida: '{name}'. "
                f"Fuentes disponibles: {disponibles}"
            )
        return cls._registry[name]

    @classmethod
    def list_sources(cls) -> list:
        """Lista los nombres de fuentes registradas."""
        return list(cls._registry.keys())

    @classmethod
    def limpiar_registro(cls) -> None:
        """Limpia el registro (util para tests)."""
        cls._registry.clear()
