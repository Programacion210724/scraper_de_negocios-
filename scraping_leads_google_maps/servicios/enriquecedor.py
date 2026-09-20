"""Enriquecedor: merge cross-source con field_sources.

Principio: el enriquecimiento complementa, nunca sobrescribe.
Con una sola fuente, cada grupo de dedup_key tiene 1 lead — passthrough.
Con multiples fuentes, fusiona field-by-field conservando la prioridad.

Preparado para Fase 4 (cuando DePeru u otra fuente se agregue).
"""
import copy
import logging
from typing import List

from modelos.lead import Lead
from servicios.deduplicator import Deduplicator

logger = logging.getLogger(__name__)


class Enriquecedor:
    """Enriquecimiento cross-source: merge de leads de distintas fuentes.

    1. Agrupa leads por dedup_key (usa Deduplicator).
    2. Ordena cada grupo por: priority(fuente) DESC, confianza ML DESC.
    3. Toma el lead con mayor prioridad como base.
    4. Para cada campo comun: si base no tiene valor, copia del siguiente.
    5. Registra field_sources[campo] = fuente que aporto el valor.
    6. Consolida raw_fields de todas las fuentes.
    """

    def __init__(self, deduplicator: Deduplicator = None):
        self.deduplicator = deduplicator or Deduplicator()

    def enriquecer(self, leads: List[Lead]) -> List[Lead]:
        """Agrupa por dedup_key y fusiona cross-source.

        Con una sola fuente, cada grupo tiene 1 lead → passthrough.
        """
        if not leads:
            return []

        grupos = {}
        for lead in leads:
            key = self.deduplicator.calcular_dedup_key(lead)
            grupos.setdefault(key, []).append(lead)

        resultado = []
        for key, grupo in grupos.items():
            if len(grupo) == 1:
                resultado.append(grupo[0])
            else:
                merged = self._merge_grupo(grupo)
                resultado.append(merged)

        if len(leads) > len(resultado):
            logger.info(
                "Enriquecimiento: %d leads fusionados en %d grupos unicos",
                len(leads) - len(resultado), len(resultado),
            )
        else:
            logger.debug(
                "Enriquecimiento: %d leads, sin fusiones (single source)",
                len(leads),
            )
        return resultado

    def _merge_grupo(self, grupo: List[Lead]) -> Lead:
        """Fusiona un grupo de leads de distintas fuentes.

        Sort: mayor priority(fuente) DESC, luego mayor confianza ML DESC.
        Base = primer lead despues de sort.
        """
        grupo_ordenado = sorted(
            grupo,
            key=lambda l: (self._get_priority(l), l.confianza or 0),
            reverse=True,
        )

        base = copy.deepcopy(grupo_ordenado[0])

        for lead in grupo_ordenado[1:]:
            for campo in Lead.COMMON_FIELDS:
                valor_actual = getattr(base, campo, None)
                valor_nuevo = getattr(lead, campo, None)
                if not valor_actual and valor_nuevo:
                    setattr(base, campo, valor_nuevo)
                    base.field_sources[campo] = lead.fuente
            # Consolidar raw_fields
            base.raw_fields.update(lead.raw_fields)
            # Consolidar field_sources existentes
            for k, v in lead.field_sources.items():
                if k not in base.field_sources:
                    base.field_sources[k] = v

        return base

    def _get_priority(self, lead: Lead) -> int:
        """Obtiene la prioridad de la fuente del lead (lazy import)."""
        try:
            from servicios.fabrica_scrapers import ScraperFactory
            scraper = ScraperFactory.get(lead.fuente)
            return scraper.source_config.priority
        except Exception:
            return 0
