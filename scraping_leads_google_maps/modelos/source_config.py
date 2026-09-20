"""Configuracion de una fuente de scraping."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class SourceConfig:
    """Configuracion estatica de una fuente de scraping.

    Attributes:
        display_name: Nombre legible para el usuario final.
        priority: Prioridad de la fuente (10=google_maps, 8=deperu, 6=pagination, 3=osm).
        country: Codigo ISO de pais ("PE", "global").
        requires_proxy: Si la fuente requiere proxy para navegar.
        enabled: Si la fuente esta habilitada para uso.
        rate_limit: Limite de solicitudes por segundo (None = sin limite).
        supports_deep: Si la fuente soporta modo de extraccion profundo.
    """
    display_name: str
    priority: int
    country: str = "PE"
    requires_proxy: bool = False
    enabled: bool = True
    rate_limit: Optional[float] = None
    supports_deep: bool = False
