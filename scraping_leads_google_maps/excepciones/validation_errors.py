"""Excepciones de validacion de leads.

Se usan en el pipeline V2 para marcar leads que no cumplen
las reglas minimas de calidad (nombre vacio, etc.).
"""
from typing import Optional


class ValidationError(Exception):
    """Error base para validacion de leads.

    Attributes:
        message: Descripcion del error.
        campo: Nombre del campo que fallo.
        valor: Valor del campo que fallo.
    """

    def __init__(self, message: str, campo: str = "", valor: str = ""):
        self.campo = campo
        self.valor = valor
        super().__init__(message)


class InvalidLeadError(ValidationError):
    """Lead invalido: no cumple las reglas minimas de validacion.

    Attributes:
        lead_info: Informacion resumida del lead para logging.
    """

    def __init__(self, message: str, lead_info: str = ""):
        self.lead_info = lead_info
        super().__init__(message)
