"""Excepciones especificas de fuentes de scraping."""
from typing import Optional


class SourceError(Exception):
    """Error base para fuentes de scraping.

    Attributes:
        source: Nombre de la fuente que fallo.
        message: Descripcion del error.
        retryable: Si el error es reintentable.
    """

    def __init__(self, source: str, message: str, retryable: bool = False):
        self.source = source
        self.message = message
        self.retryable = retryable
        super().__init__(f"[{source}] {message} (retryable={retryable})")


class SourceTimeoutError(SourceError):
    """Error de timeout en una fuente de scraping."""

    def __init__(self, source: str, message: str = "Timeout agotado", retryable: bool = True):
        super().__init__(source, message, retryable=retryable)


class CaptchaError(SourceError):
    """Error de captcha o verificacion de humano en una fuente."""

    def __init__(self, source: str, message: str = "Captcha detectado", retryable: bool = True):
        super().__init__(source, message, retryable=retryable)
