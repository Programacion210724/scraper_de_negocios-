"""Adapter de Google Maps — conecta el core con la arquitectura V2.

Importa scrape_google_maps() de scraper.scraper (read-only, NO modifica el core)
y convierte el output dict[] al modelo unificado Lead[]. El core sigue
produciendo los mismos campos: nombre, direccion, telefono, ciudad,
categoria, maps_url, categoria_pred, confianza.
"""
import logging
import threading
from typing import List

from scraper.scraper import scrape_google_maps
from scraper.scraper import _normalizar_maps_url

from modelos.lead import Lead
from modelos.scrape_request import ScrapeRequest
from modelos.source_config import SourceConfig
from fuentes.base import ScraperInterface
from excepciones.source_errors import SourceError, CaptchaError, SourceTimeoutError

logger = logging.getLogger(__name__)


class GoogleMapsSource(ScraperInterface):
    """Adapter read-only que envuelve scrape_google_maps() del core.

    El core (scraper.scraper) sigue siendo el unico encargado del scraping
    de Google Maps: Playwright, batch processing, captcha detection, ML filter.
    Este adapter solo traduce el output dict[] al modelo Lead unificado.
    """

    @property
    def source_name(self) -> str:
        return "google_maps"

    @property
    def source_config(self) -> SourceConfig:
        return SourceConfig(
            display_name="Google Maps",
            priority=10,
            country="PE",
            requires_proxy=True,
            enabled=True,
            supports_deep=True,
        )

    def build_search_url(self, keyword: str, city: str) -> str:
        """Construye la URL de busqueda de Google Maps."""
        search_query = f"{keyword} {city}".replace(" ", "+")
        return f"https://www.google.com/maps/search/{search_query}"

    def get_metadata(self) -> dict:
        return {
            "rate_limit": None,
            "captcha_required": True,
            "batch_size": 10,
        }

    async def scrape(
        self,
        request: ScrapeRequest,
        cancel_event: threading.Event,
    ) -> List[Lead]:
        """Ejecuta scraping de Google Maps y convierte dict[] a Lead[].

        IMPORTANT: No normaliza, valida ni deduplica. Ese pipeline lo aplica
        el orquestador. Este metodo solo traduce el output del core al modelo
        unificado.

        Args:
            request: ScrapeRequest con keyword, city, limit, mode, job_id.
            cancel_event: threading.Event para cancelacion colaborativa.

        Returns:
            List[Lead]: Leads crudos del core, convertidos al modelo unificado.

        Raises:
            CaptchaError: Si se detecta captcha durante el scraping.
            SourceTimeoutError: Si el scraping excede el timeout.
            SourceError: Cualquier otro error del core.
        """
        logger.info(
            "Iniciando scraping Google Maps: keyword=%s city=%s limit=%d mode=%s",
            request.keyword, request.city, request.limit, request.mode,
        )

        try:
            # El core ya aplica filter_and_group (ML) internamente
            # antes de retornar. No se duplica esa logica aqui.
            raw_results = await scrape_google_maps(
                keyword=request.keyword,
                city=request.city,
                limit=request.limit,
                mode=request.mode,
                cancel_event=cancel_event,
            )
        except Exception as e:
            message = str(e).lower()
            if "captcha" in message:
                logger.warning("Captcha detectado en Google Maps: %s", e)
                raise CaptchaError("google_maps", str(e), retryable=True)
            if "timeout" in message:
                logger.warning("Timeout en Google Maps: %s", e)
                raise SourceTimeoutError("google_maps", str(e), retryable=True)
            logger.error(
                "Technical summary: error in scrape_google_maps for source=google_maps | "
                "Resumen: error durante el scraping de Google Maps. Reintentalo en unos momentos."
            )
            raise SourceError("google_maps", str(e), retryable=False)

        if not raw_results:
            logger.info(
                "Google Maps: sin resultados para '%s' en '%s'",
                request.keyword, request.city,
            )
            return []

        leads = [self._dict_a_lead(d, request) for d in raw_results]
        logger.info("Google Maps: %d leads extraidos", len(leads))
        return leads

    def _dict_a_lead(self, d: dict, request: ScrapeRequest) -> Lead:
        """Convierte un dict del core al modelo Lead unificado.

        Mapeo:
            nombre -> nombre (directo)
            direccion -> direccion (directo)
            telefono -> telefono (directo)
            ciudad -> ciudad (directo)
            categoria -> categoria_busqueda (rename)
            maps_url -> url_raw + maps_url (dual)
            categoria_pred -> categoria_pred (directo)
            confianza -> confianza (directo)
            fuente = 'google_maps' (hardcodeado en adapter)
        """
        maps_url = d.get("maps_url", "") or ""

        lead = Lead(
            nombre=d.get("nombre", ""),
            direccion=d.get("direccion", ""),
            telefono=d.get("telefono", ""),
            ciudad=d.get("ciudad", ""),
            categoria_busqueda=d.get("categoria", ""),
            url_raw=maps_url,
            fuente="google_maps",
            maps_url=maps_url,
            categoria_pred=d.get("categoria_pred"),
            confianza=d.get("confianza"),
            job_id=request.job_id or "",
        )

        # Attribution: todos los campos vienen de google_maps
        for campo in [
            "nombre", "direccion", "telefono", "ciudad",
            "categoria_busqueda", "maps_url", "categoria_pred", "confianza",
        ]:
            lead.field_sources[campo] = "google_maps"

        # Almacenar datos raw del core para auditoria
        lead.raw_fields["google_maps"] = dict(d)

        return lead
