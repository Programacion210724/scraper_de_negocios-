"""Modelo de solicitud de scraping unificado."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScrapeRequest:
    """Parametros de una solicitud de scraping.

    Attributes:
        keyword: Palabra clave de busqueda.
        city: Ciudad donde buscar (campo del contrato API).
        limit: Numero maximo de leads deseados.
        mode: Modo de extraccion ("simple" o "deep").
        source: Nombre de la fuente a usar.
        job_id: Identificador del job asociado.
        proxy_enabled: Si se debe usar proxy.
        extra_params: Parametros adicionales especificos de la fuente.
    """
    keyword: str
    city: str
    limit: int = 20
    mode: str = "simple"
    source: str = "google_maps"
    job_id: Optional[str] = None
    proxy_enabled: bool = False
    extra_params: dict = field(default_factory=dict)
