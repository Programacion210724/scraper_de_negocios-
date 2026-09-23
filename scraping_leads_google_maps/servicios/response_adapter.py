"""Adaptador de respuesta: Lead[] -> formato legacy dict[].

Preserva el contrato del frontend y Google Sheets, que consumen:
  nombre, direccion, telefono, ciudad, categoria, maps_url,
  categoria_pred, confianza.

El modelo Lead usa `categoria_busqueda` (no `categoria`). Este adaptador
realiza el rename para compatibilidad con el formato legacy.
"""
from typing import List

from modelos.lead import Lead


def leads_a_dict_legacy(leads: List[Lead]) -> list:
    """Convierte Lead[] al formato dict[] esperado por el frontend.

    Mapeos:
        categoria_busqueda -> categoria
        maps_url           -> maps_url (fallback a url_raw)
        categoria_pred     -> categoria_pred
        confianza          -> confianza
    """
    return [
        {
            "nombre": lead.nombre,
            "direccion": lead.direccion,
            "telefono": lead.telefono,
            "ciudad": lead.ciudad,
            "categoria": lead.categoria_busqueda,
            "maps_url": lead.maps_url or lead.url_raw or "",
            "categoria_pred": lead.categoria_pred,
            "confianza": lead.confianza,
        }
        for lead in leads
    ]
