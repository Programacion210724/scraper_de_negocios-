"""Validador de leads: reglas minimas de calidad.

Regla estricta unica: nombre no puede estar vacio.
Otros campos (telefono, direccion, maps_url) se validan por formato
si existen, pero su ausencia no elimina el lead — otra fuente
puede complementarlos en el enriquecimiento cross-source.
"""
import logging
from typing import List

from modelos.lead import Lead

logger = logging.getLogger(__name__)


class Validador:
    """Valida leads con regla estricta unica: nombre obligatorio."""

    def validar_lead(self, lead: Lead) -> bool:
        """Valida un lead individual.

        Solo descarta leads con nombre vacio. Otros campos ausentes
        no causan descarte — pueden ser completados por otra fuente.

        Args:
            lead: Lead a validar.

        Returns:
            True si el lead es valido (nombre non-empty).
            False si debe descartarse.
        """
        if not lead.nombre or not lead.nombre.strip():
            logger.warning(
                "Lead descartado: nombre vacio (fuente=%s, job_id=%s)",
                lead.fuente, lead.job_id,
            )
            return False
        return True

    def validar(self, leads: List[Lead]) -> List[Lead]:
        """Filtra la lista, conservando leads con nombre no vacio.

        No descarta por ausencia de telefono, direccion o maps_url.
        Registra calidad de cada lead para priorizacion futura.
        """
        validos = []
        for lead in leads:
            if self.validar_lead(lead):
                # Marcar calidad sin descartar
                lead.calidad = self.calidad_lead(lead)
                validos.append(lead)
        descartados = len(leads) - len(validos)
        if descartados > 0:
            logger.info(
                "Validacion: %d/%d leads validos "
                "(descartados %d por nombre vacio)",
                len(validos), len(leads), descartados,
            )
        return validos

    def calidad_lead(self, lead: Lead) -> str:
        """Evalua la calidad del lead segun campos completos.

        Returns:
            "completa" — nombre + telefono + direccion + maps_url
            "parcial"  — nombre + al menos un campo mas
            "minima"   — solo nombre
        """
        campos = 0
        if lead.nombre:
            campos += 1
        if lead.telefono:
            campos += 1
        if lead.direccion:
            campos += 1
        if lead.maps_url or lead.url_raw:
            campos += 1

        if campos >= 4:
            return "completa"
        elif campos >= 2:
            return "parcial"
        return "minima"
