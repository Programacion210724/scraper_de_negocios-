"""Orquestador: pipeline completo de scraping V2.

Pipeline Fase 2:
  scrape -> normalize -> validate -> dedup L1 -> dedup L2 (stub)
  -> dedup L3 (no-op) -> enrich (passthrough) -> classify -> result

NO toca el core. Usa adapter pattern para fuentes.
"""
import logging
import threading
from typing import List

from modelos.lead import Lead
from modelos.scrape_request import ScrapeRequest
from servicios.fabrica_scrapers import ScraperFactory
from servicios.normalizador import Normalizador
from servicios.validador import Validador
from servicios.deduplicator import Deduplicator
from servicios.enriquecedor import Enriquecedor
from servicios.clasificador_servicio import ClasificadorServicio

logger = logging.getLogger(__name__)


class Orquestador:
    """Orquestador del pipeline V2 completo.

    Inyecta todas las dependencias del pipeline:
    Normalizador, Validador, Deduplicator, Enriquecedor, ClasificadorServicio.
    """

    def __init__(self):
        self.normalizador = Normalizador()
        self.validador = Validador()
        self.deduplicator = Deduplicator(self.normalizador)
        self.enriquecedor = Enriquecedor(self.deduplicator)
        self.clasificador = ClasificadorServicio()

    async def orquestar(
        self,
        request: ScrapeRequest,
        cancel_event: threading.Event = None,
    ) -> List[Lead]:
        """Ejecuta el pipeline completo de scraping.

        Args:
            request: ScrapeRequest con keyword, city, limit, mode, source.
            cancel_event: threading.Event para cancelacion colaborativa.

        Returns:
            List[Lead]: Leads procesados, validados, deduplicados y clasificados.
        """
        logger.info(
            "Orquestador: iniciando pipeline | source=%s keyword=%s city=%s limit=%d mode=%s",
            request.source, request.keyword, request.city, request.limit, request.mode,
        )

        # 1. Resolver fuente via factory
        scraper = ScraperFactory.get(request.source)
        logger.info("Orquestador: fuente resuelta: %s", scraper.source_name)

        # 2. Scraping (adapter -> core read-only)
        leads_post_normalize = await scraper.scrape(request, cancel_event)
        logger.info("Orquestador: %d leads extraidos de %s", len(leads_post_normalize), request.source)

        # 3. Normalizar
        for lead in leads_post_normalize:
            self.normalizador.normalizar_lead(lead)
        logger.info("Orquestador: normalizados %d leads", len(leads_post_normalize))

        # 4. Validar (solo descarta nombre vacio)
        leads_valid = self.validador.validar(leads_post_normalize)
        logger.info("Orquestador: %d leads validos", len(leads_valid))

        # 5. L1: deduplicacion intra-scrape (in-memory, ACTIVE)
        leads_dedup_l1 = self.deduplicator.dedup_L1(leads_valid)
        logger.info("Orquestador: %d leads tras L1 dedup", len(leads_dedup_l1))

        # 6. L2: deduplicacion cross-session (STUB — sin BD en Fase 2)
        leads_dedup_l2 = self.deduplicator.dedup_L2(leads_dedup_l1, repository=None)
        logger.info("Orquestador: %d leads tras L2 dedup (stub)", len(leads_dedup_l2))

        # 7. L3: deduplicacion cross-source (NO-OP — single source)
        leads_dedup_l3 = self.deduplicator.dedup_L3(leads_dedup_l2)
        logger.info("Orquestador: %d leads tras L3 dedup", len(leads_dedup_l3))

        # 8. Enriquecimiento (passthrough con single source)
        leads_enriched = self.enriquecedor.enriquecer(leads_dedup_l3)
        logger.info("Orquestador: %d leads tras enriquecimiento", len(leads_enriched))

        # 9. ML clasificacion (wrapper read-only del core classifier)
        leads_final = self.clasificador.clasificar(leads_enriched, keyword=request.keyword)
        logger.info("Orquestador: pipeline completado. %d leads finales", len(leads_final))

        return leads_final
