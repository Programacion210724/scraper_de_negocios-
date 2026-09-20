"""Normalizador de campos para leads unificados.

Recibe un Lead crudo (con datos del core o de cualquier fuente) y
normaliza campos para deduplicacion consistente, almacenamiento
limpio en BD y comparacion entre fuentes.

Reutiliza _normalizar_maps_url() del core scraper.scraper (import
read-only, no se copia codigo).
"""
import logging
import re
import unicodedata

from modelos.lead import Lead

logger = logging.getLogger(__name__)

# Import read-only del normalizador de URLs de Google Maps del core
try:
    from scraper.scraper import _normalizar_maps_url
except ImportError:
    _normalizar_maps_url = None
    logger.warning("No se pudo importar _normalizar_maps_url de scraper.scraper")


class Normalizador:
    """Normaliza campos de leads para deduplicacion y almacenamiento."""

    # Sufijos legales a remover del nombre
    SUFIJOS_LEGADOS = [
        "S.A.C.", "S.A.", "S.R.L.", "E.I.R.L.", "E.I.R.", "S.N.",
        "S.L.", "S.L.L.", "A.C.", "Corporacion", "Corp.",
    ]

    # Abreviaturas comunes en direcciones
    ABREVIATURAS = {
        "av.": "av",
        "avda.": "av",
        "avenida": "av",
        "clr.": "calle",
        "cl.": "calle",
        "calle": "calle",
        "cra.": "carrera",
        "carrera": "carrera",
        "jr.": "junior",
        "pasaje": "pasaje",
        "pje.": "pasaje",
        "pz.": "plaza",
        "plaza": "plaza",
        "n.º": "n",
        "nro.": "n",
        "num.": "n",
        "numero": "n",
    }

    # Codigos de pais para normalizacion de telefonos
    _COUNTRY_PREFIXES = {
        "PE": "51",
        "ES": "34",
        "MX": "52",
        "CO": "57",
        "CL": "56",
        "AR": "54",
        "US": "1",
    }

    @staticmethod
    def _limpiar_acentos(text: str) -> str:
        """Elimina acentos usando normalizacion NFD."""
        text = unicodedata.normalize("NFD", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        return text

    def normalizar_telefono(self, raw: str, country_code: str = "PE") -> str:
        """Convierte a formato E.164.

        Ejemplos (Peru, country_code='PE'):
            '999123456'   (movil)     -> '+51999123456'
            '01-1234567'  (fijo Lima) -> '+5111234567'
            '+51 999 123 456'         -> '+51999123456'
            '123' (corto)             -> '' (invalido)

        Args:
            raw: Telefono en formato crudo.
            country_code: Codigo ISO de pais (default PE).

        Returns:
            Telefono en formato E.164 o cadena vacia si es invalido.
        """
        if not raw:
            return ""

        # Extraer solo digitos
        digits = re.sub(r"\D", "", str(raw).strip())
        if not digits:
            return ""

        prefix = self._COUNTRY_PREFIXES.get(country_code, "")
        if not prefix:
            # Sin codigo de pais conocido: asumir internacional
            if len(digits) >= 8 and not digits.startswith("0"):
                return f"+{digits}"
            return ""

        if country_code == "PE":
            # Caso: ya incluye codigo de pais (+51 o 51)
            if digits.startswith(prefix):
                rest = digits[len(prefix):]
                # Quitar 0 inicial si existe (Lima: 01 -> 1)
                if rest.startswith("0"):
                    rest = rest[1:]
                if len(rest) >= 7:
                    return f"+{prefix}{rest}"
                return ""

            # Caso: numero local con 0 inicial (ej: 01-1234567)
            if digits.startswith("0"):
                rest = digits[1:]
                if len(rest) >= 7:
                    return f"+{prefix}{rest}"
                return ""

            # Caso: numero local sin 0 inicial
            # Movil Peru: 9 digitos empezando con 9
            if len(digits) == 9 and digits[0] == "9":
                return f"+{prefix}{digits}"
            # Fijo: asumir suficiente longitud
            if len(digits) >= 7:
                return f"+{prefix}{digits}"
            return ""

        # Para otros paises
        if digits.startswith(prefix):
            rest = digits[len(prefix):]
            if len(rest) >= 7:
                return f"+{prefix}{rest}"

        if len(digits) >= 8 and not digits.startswith("0"):
            return f"+{digits}"

        return ""

    def normalizar_nombre(self, raw: str) -> str:
        """Normaliza un nombre: lowercase, strip acentos, quitar sufijos legales.

        Ejemplo:
            'Ferreteria El Constructor S.A.C.' -> 'ferreteria el constructor'
        """
        if not raw:
            return ""

        text = raw.strip()
        # Strip acentos
        text = self._limpiar_acentos(text)
        # Lowercase
        text = text.lower()
        # Quitar sufijos legales (procesar los mas largos primero para evitar
        # matches parciales, ej: S.A.C. antes que S.A.)
        for sufijo in sorted(self.SUFIJOS_LEGADOS, key=len, reverse=True):
            pattern = re.escape(sufijo.lower())
            # Match sufijo rodeado de espacios o bordes de string
            text = re.sub(
                rf"(?:^|\s){pattern}(?:\s|$)", " ",
                text, flags=re.IGNORECASE,
            )
        # Limpiar espacios multiples
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def normalizar_direccion(self, raw: str) -> str:
        """Normaliza abreviaturas y estandariza formato de direcciones.

        Ejemplo:
            'Av. Arequipa 123' -> 'av arequipa 123'
        """
        if not raw:
            return ""

        text = raw.strip()
        # Strip acentos
        text = self._limpiar_acentos(text)
        text = text.lower()
        # Normalizar abreviaturas (procesar las mas largas primero)
        for abrev in sorted(self.ABREVIATURAS.keys(), key=len, reverse=True):
            expand = self.ABREVIATURAS[abrev]
            pattern = re.escape(abrev.lower())
            # Match abreviatura al inicio de palabra (sin requerir  al final
            # porque algunas terminan en '.' que no es word char)
            text = re.sub(
                rf"(?:^|\s){pattern}", f" {expand}",
                text, flags=re.IGNORECASE,
            )
        # Quitar puntuacion extra
        text = re.sub(r"[^\w\s]", " ", text)
        # Limpiar espacios multiples
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def normalizar_url(self, url: str, fuente: str) -> str:
        """Normaliza una URL segun la fuente.

        - google_maps: reutiliza _normalizar_maps_url() del core (import read-only)
        - otras fuentes: quita query string y fragmento
        """
        if not url:
            return ""

        if fuente == "google_maps" and _normalizar_maps_url:
            return _normalizar_maps_url(url)

        # Fallback: quitar query string y fragmento para cualquier otra fuente
        text = url.strip()
        text = re.sub(r"\?(.*)$", "", text)
        text = re.sub(r"#.*$", "", text)
        return text.strip()

    def normalizar_lead(self, lead: Lead) -> Lead:
        """Aplica todas las normalizaciones a un Lead.

        Normaliza telefono, nombre, direccion y URLs.
        El nombre normalizado se almacena en el atributo nombre_norm
        para uso posterior en deduplicacion.
        """
        lead.telefono = self.normalizar_telefono(lead.telefono)
        lead.nombre_norm = self.normalizar_nombre(lead.nombre)
        if lead.direccion:
            lead.direccion = self.normalizar_direccion(lead.direccion)
        if lead.url_raw:
            lead.url_raw = self.normalizar_url(lead.url_raw, lead.fuente)
        if lead.maps_url:
            lead.maps_url = self.normalizar_url(lead.maps_url, lead.fuente)
        return lead
