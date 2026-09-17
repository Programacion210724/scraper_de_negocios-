"""Interfaz base para scrapers de fuentes (patron Strategy).

Define el contrato comun para todas las fuentes de scraping.
Cada fuente implementa este ABC y se registra en el ScraperFactory.
"""
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from modelos.source_config import SourceConfig

if TYPE_CHECKING:
    from modelos.lead import Lead
    from modelos.scrape_request import ScrapeRequest


class ScraperInterface(ABC):
    """CONTRATO comun para todas las fuentes de scraping."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identificador unico (ej: 'google_maps', 'deperu')."""

    @property
    @abstractmethod
    def source_config(self) -> SourceConfig:
        """Configuracion: display_name, priority, country, requires_proxy."""

    @abstractmethod
    async def scrape(
        self,
        request: "ScrapeRequest",
        cancel_event: threading.Event | None = None,
    ) -> list["Lead"]:
        """Ejecuta el scraping.

        Args:
            request: ScrapeRequest con keyword, city, limit, mode, job_id.
            cancel_event: threading.Event opcional para cancelacion. None si no aplica.

        Returns:
            list[Lead]: Resultado nativo de la fuente. Dependiendo de la
                        implementacion concreta, puede incluir normalizacion
                        ligera, deduplicacion intra-scrape o clasificacion ML;
                        el orquestador trata estos campos de forma idempotente.

        Raises:
            SourceError(retryable=True/False): error con metadata de reintentabilidad.
        """

    @abstractmethod
    def build_search_url(self, keyword: str, city: str) -> str:
        """Construye la URL de busqueda para esta fuente."""

    def get_metadata(self) -> dict:
        """Metadatos opcionales: rate_limit, captcha_required, etc."""
        return {}
