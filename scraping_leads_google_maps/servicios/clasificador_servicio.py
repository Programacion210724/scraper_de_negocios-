"""Wrapper read-only del clasificador ML del core.

IMPORTA scraper.classifier.classifier (read-only, NO modifica el core).
Reclasiifica solo leads PENDIENTES — si el core (GoogleMapsSource) ya
aplico filter_and_group, categoria_pred y confianza ya estan set;
el wrapper omite la reclasificacion para evitar doble procesamiento ML.

Futuras fuentes sin ML (ej. DePeru) tendran categoria_pred=None y
seran clasificadas aqui.
"""
import logging
from typing import List

from scraper.classifier import classifier as _classifier
from modelos.lead import Lead

logger = logging.getLogger(__name__)


class ClasificadorServicio:
    """Wrapper read-only del core LeadClassifier.

    Convierte Lead[] a list[dict], llama classifier.filter_and_group()
    del core (read-only import), y actualiza categoria_pred + confianza.

    Optimizacion: detecta leads ya clasificados por el core y los
    preserva sin reclasificar (evita doble processing ML).
    """

    def clasificar(
        self,
        leads: List[Lead],
        keyword: str = "",
        force: bool = False,
    ) -> List[Lead]:
        """Clasifica ML solo los leads pendientes.

        Un Lead esta clasificado si tiene categoria_pred != None Y confianza != None.
        Si force=True, reclasifica todos (solo para testing/debugging).

        Args:
            leads: Leads a clasificar.
            keyword: Palabra clave (para ordenar por categoria en filter_and_group).
            force: Si True, reclasifica incluso leads ya clasificados.

        Returns:
            List[Lead] en el MISMO orden original.
        """
        if not leads:
            return leads

        # Nota de orden:
        # - leads ya clasificados (categoria_pred y confianza set): se conservan
        #   tal cual, preservando el orden original.
        # - leads pendientes: se delegan al Legacy Core (filter_and_group), que
        #   puede reordenarlos por categoria/confianza.
        # - force=True: obliga a clasificar todos, usando la misma ruta anterior.

        # --- Partir leads en clasificados y pendientes ---
        if not force:
            clasificados = [
                l for l in leads
                if l.categoria_pred is not None and l.confianza is not None
            ]
            pendientes = [
                l for l in leads
                if l.categoria_pred is None or l.confianza is None
            ]
        else:
            clasificados = []
            pendientes = list(leads)

        # --- Caso: todos ya clasificados ---
        if not pendientes:
            logger.info(
                "Clasificacion ML: omitida (%d leads ya clasificados por core). "
                "Ningun lead pendiente.",
                len(clasificados),
            )
            return leads  # Preservar orden original

        # --- Caso: todos pendientes ---
        if not clasificados:
            logger.info(
                "Clasificacion ML: %d leads sin clasificar, aplicando clasificacion completa",
                len(pendientes),
            )
            return self._clasificar_lote(pendientes, keyword)

        # --- Caso: mezcla ---
        logger.info(
            "Clasificacion ML: %d clasificados preservados, %d pendientes a clasificar",
            len(clasificados), len(pendientes),
        )
        clasificados_pendientes = self._clasificar_lote(pendientes, keyword)

        # --- Reintegrar preservando orden original ---
        clasificados_set = set(id(l) for l in clasificados)
        result = []
        pendientes_iter = iter(clasificados_pendientes)
        for lead in leads:
            if id(lead) in clasificados_set:
                result.append(lead)
            else:
                result.append(next(pendientes_iter))
        return result

    def _clasificar_lote(self, leads: List[Lead], keyword: str) -> List[Lead]:
        """Aplica filter_and_group del core a un lote de leads pendientes.

        Convierte Lead[] a list[dict] (con _lead_ref para mapear resultados),
        llama classifier.filter_and_group() (read-only), y actualiza
        categoria_pred + confianza en cada Lead.
        """
        if not leads:
            return leads

        dicts = []
        for lead in leads:
            d = {
                "nombre": lead.nombre,
                "direccion": lead.direccion or "",
                "telefono": lead.telefono or "",
                "ciudad": lead.ciudad or "",
                "categoria": lead.categoria_busqueda or "",
                "maps_url": lead.maps_url or lead.url_raw or "",
                "_lead_ref": lead,
            }
            dicts.append(d)

        try:
            resultados = _classifier.filter_and_group(dicts, keyword=keyword)
        except Exception as e:
            logger.warning("Clasificacion ML no aplicada: %s", e)
            for d in dicts:
                d["_lead_ref"].categoria_pred = None
                d["_lead_ref"].confianza = None
            return leads

        leads_result = []
        for d in resultados:
            lead = d.get("_lead_ref")
            if lead is not None:
                lead.categoria_pred = d.get("categoria_pred")
                lead.confianza = d.get("confianza")
                leads_result.append(lead)
            else:
                logger.debug("Lead ruidoso detectado en clasificacion, omitido")

        logger.info("Clasificacion ML aplicada: %d leads clasificados", len(leads_result))
        return leads_result
