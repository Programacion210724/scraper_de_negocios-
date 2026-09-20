"""Deduplicador multi-source: L1 intra-scrape, L2 cross-session, L3 cross-source.

L1: Set de dedup_keys en memoria (por job) — descarta duplicados intra-scrape.
L2: Lookup en BD por dedup_key — cross-session (STUB en Fase 2, BD en Fase 3).
L3: Fuzzy match entre leads de distintas fuentes — cross-source (no-op con 1 source).

NOTA: el core (scraper.scraper._dedup_key) ya hace deduplicacion intra-scrape
sobre dicts. Este Deduplicator opera sobre Lead objects (post-normalizacion),
complementando al core sin reemplazarlo.
"""
import hashlib
import logging
from difflib import SequenceMatcher
from typing import List, Optional

from modelos.lead import Lead
from servicios.normalizador import Normalizador

logger = logging.getLogger(__name__)


class Deduplicator:
    """Deduplicacion multi-nivel de leads.

    Construido sobre el Normalizador para claves consistentes.
    Cada nivel puede activarse/desactivarse segun la disponibilidad
    de infraestructura (BD para L2, multi-source para L3).
    """

    def __init__(self, normalizador: Optional[Normalizador] = None):
        self.normalizador = normalizador or Normalizador()

    def calcular_dedup_key(self, lead: Lead) -> str:
        """Calcula la clave de deduplicacion.

        Prioridad: coordenadas -> telefono -> nombre+ciudad -> url -> hash.
        Usa el Normalizador para valores consistentes.
        """
        # Coords (mas preciso)
        if lead.latitud and lead.longitud:
            return f"coords:{round(lead.latitud, 5)}:{round(lead.longitud, 5)}"

        # Telefono normalizado
        telefono = self.normalizador.normalizar_telefono(lead.telefono)
        if telefono:
            return f"phone:{telefono}"

        # Nombre + ciudad normalizados
        nombre = self.normalizador.normalizar_nombre(lead.nombre)
        if nombre and lead.ciudad:
            ciudad_norm = lead.ciudad.strip().lower()
            return f"name:{nombre}|city:{ciudad_norm}"

        # URL normalizada
        if lead.url_raw:
            url = self.normalizador.normalizar_url(lead.url_raw, lead.fuente)
            if url:
                return f"url:{url}"

        # Hash fallback
        return f"hash:{self._hash_lead(lead)}"

    def _hash_lead(self, lead: Lead) -> str:
        """Hash estable del lead para fallback de dedup_key."""
        raw = "|".join([
            lead.nombre or "",
            lead.direccion or "",
            lead.telefono or "",
            lead.ciudad or "",
            lead.url_raw or lead.maps_url or "",
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def dedup_L1(self, leads: List[Lead]) -> List[Lead]:
        """L1: Deduplicacion intra-scrape (in-memory set).

        Descarta duplicados dentro del mismo scraping usando dedup_key.
        Activo en Fase 2.
        """
        vistos = set()
        result = []
        for lead in leads:
            key = self.calcular_dedup_key(lead)
            if key not in vistos:
                vistos.add(key)
                result.append(lead)
        descartados = len(leads) - len(result)
        if descartados > 0:
            logger.info("L1 dedup: %d duplicados intra-scrape descartados", descartados)
        return result

    def dedup_L2(self, leads: List[Lead], repository: Optional[object] = None) -> List[Lead]:
        """L2: Deduplicacion cross-session (BD lookup).

        En Fase 2, no existe base de datos. Retorna leads sin cambios
        y registra un log claro. La implementacion real llega en Fase 3
        con persistencia/lead_repository.py.

        Args:
            leads: Leads a deduplicar.
            repository: Repositorio de leads (None en Fase 2).

        Returns:
            Leads sin cambios si repository es None.
        """
        if repository is None:
            logger.info(
                "L2 dedup: omitido (sin repositorio/BD en Fase 2). "
                "Se retornan %d leads sin cambios.", len(leads),
            )
            return leads
        # Implementacion futura (Fase 3):
        #   for lead in leads:
        #       key = self.calcular_dedup_key(lead)
        #       if not repository.existe_dedup_key(key):
        #           result.append(lead)
        result = []
        for lead in leads:
            key = self.calcular_dedup_key(lead)
            if not repository.existe_dedup_key(key):
                result.append(lead)
        logger.info("L2 dedup: %d duplicados cross-session descartados", len(leads) - len(result))
        return result

    def dedup_L3(self, leads: List[Lead], umbral: float = 0.95) -> List[Lead]:
        """L3: Deduplicacion cross-source (fuzzy match).

        Con una sola fuente, cada grupo de dedup_key tiene 1 lead — no-op.
        Con multiples fuentes, agrupa por dedup_key y aplica fuzzy matching
        para detectar el mismo negocio en fuentes distintas.

        Args:
            leads: Leads a deduplicar.
            umbral: Score minimo para considerar coincidencia (default 0.95 EXACT).
        """
        # Agrupar por dedup_key
        grupos: dict = {}
        for lead in leads:
            key = self.calcular_dedup_key(lead)
            grupos.setdefault(key, []).append(lead)

        result = []
        merges = 0
        for key, grupo in grupos.items():
            if len(grupo) == 1:
                # Unica fuente: no hay nada que fundir
                result.append(grupo[0])
            else:
                # Multiples fuentes: aplicar fuzzy matching (Fase 4)
                fundido = self._fundir_grupo(grupo, umbral)
                result.extend(fundido)
                merges += len(grupo) - len(fundido)

        if merges > 0:
            logger.info("L3 dedup: %d merges cross-source realizados", merges)
        else:
            logger.debug("L3 dedup: sin merges (single source o sin coincidencias)")
        return result

    def _fundir_grupo(self, grupo: List[Lead], umbral: float) -> List[Lead]:
        """Fusiona leads del mismo grupo con fuzzy matching.

        Sort: mayor prioridad de fuente primero, luego mayor confianza ML.
        El primer lead es la base; los demas se fusionan si superan el umbral.
        """
        # Sort: priority DESC, confianza DESC
        grupo_ordenado = sorted(
            grupo,
            key=lambda l: (self._get_priority(l), l.confianza or 0),
            reverse=True,
        )

        result = []
        for lead in grupo_ordenado:
            matched = False
            for base in result:
                score = self.puntuacion_coincidencia(lead, base)
                if score >= umbral:
                    self._merge_into(base, lead)
                    matched = True
                    logger.info(
                        "L3 merge: '%s' (%s) fusionado con '%s' (%s) score=%.2f",
                        lead.nombre, lead.fuente, base.nombre, base.fuente, score,
                    )
                    break
            if not matched:
                result.append(lead)
        return result

    def _get_priority(self, lead: Lead) -> int:
        """Obtiene la prioridad de la fuente del lead.

        Usa ScraperFactory (lazy import para evitar circular deps).
        Fallback: 0 si la fuente no esta registrada.
        """
        try:
            from servicios.fabrica_scrapers import ScraperFactory
            scraper = ScraperFactory.get(lead.fuente)
            return scraper.source_config.priority
        except Exception:
            return 0

    def puntuacion_coincidencia(self, lead_a: Lead, lead_b: Lead) -> float:
        """Puntuacion de coincidencia entre dos leads (0.0 a 1.0).

        Ponderaciones: telefono 40%, nombre 25%, direccion 20%,
        website 10%, coordenadas 5%.
        """
        scores = []
        weights = []

        # Telefono (40%) — match exacto
        if lead_a.telefono and lead_b.telefono:
            a = self.normalizador.normalizar_telefono(lead_a.telefono)
            b = self.normalizador.normalizar_telefono(lead_b.telefono)
            s = 1.0 if a and a == b else 0.0
            scores.append(s)
            weights.append(0.40)

        # Nombre (25%) — fuzzy
        if lead_a.nombre and lead_b.nombre:
            a = self.normalizador.normalizar_nombre(lead_a.nombre)
            b = self.normalizador.normalizar_nombre(lead_b.nombre)
            s = SequenceMatcher(None, a, b).ratio()
            scores.append(s)
            weights.append(0.25)

        # Direccion (20%) — fuzzy
        if lead_a.direccion and lead_b.direccion:
            a = self.normalizador.normalizar_direccion(lead_a.direccion)
            b = self.normalizador.normalizar_direccion(lead_b.direccion)
            s = SequenceMatcher(None, a, b).ratio()
            scores.append(s)
            weights.append(0.20)

        # Website (10%) — match exacto
        if lead_a.website and lead_b.website:
            s = 1.0 if lead_a.website == lead_b.website else 0.0
            scores.append(s)
            weights.append(0.10)

        # Coordenadas (5%) — distancia haversine
        if lead_a.latitud and lead_b.latitud and lead_a.longitud and lead_b.longitud:
            dist_m = self._haversine(lead_a, lead_b)
            s = max(0, 1 - dist_m / 50)
            scores.append(s)
            weights.append(0.05)

        if not scores:
            return 0.0
        return sum(s * w for s, w in zip(scores, weights)) / sum(weights)

    @staticmethod
    def _haversine(lead_a: Lead, lead_b: Lead) -> float:
        """Distancia en metros entre dos coordenadas."""
        from math import radians, sin, cos, sqrt, atan2
        lat1 = radians(lead_a.latitud)
        lon1 = radians(lead_a.longitud)
        lat2 = radians(lead_b.latitud)
        lon2 = radians(lead_b.longitud)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return 6371000 * c  # radio tierra en metros

    def _merge_into(self, base: Lead, otro: Lead) -> None:
        """Fusiona campos de 'otro' en 'base' (base tiene prioridad).

        Principio: el enriquecimiento complementa, nunca sobrescribe.
        """
        for campo in Lead.COMMON_FIELDS:
            valor_actual = getattr(base, campo, None)
            valor_nuevo = getattr(otro, campo, None)
            if not valor_actual and valor_nuevo:
                setattr(base, campo, valor_nuevo)
                base.field_sources[campo] = otro.fuente
        # Consolidar raw_fields
        base.raw_fields.update(otro.raw_fields)
