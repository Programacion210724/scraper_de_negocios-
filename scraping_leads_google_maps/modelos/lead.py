"""Modelo unificado de Lead para multi-source.

Este dataclass absorbe el output del core scraper.scraper.scrape_google_maps
y extiende con campos para futuras fuentes (DePeru, Paginas Amarillas, etc.).

Convenciones:
    - Todos los campos comunes del negocio estan definidos explicitamente.
    - Los campos especificos de fuente van en raw_fields (dict) para no
      tocar el modelo al agregar nuevas fuentes.
    - field_sources (dict) registra que fuente aporto cada campo, para
      el enriquecimiento cross-source.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, ClassVar, Any


@dataclass
class Lead:
    """Lead unificado multi-source.

    Datos comunes del negocio (todos los negocios tienen estos conceptos)
    estan en campos explicitos. Los datos especificos de fuente van en
    raw_fields para mantener el modelo estable.
    """

    # === DATOS COMUNES DEL NEGOCIO (todos los negocios) ===
    nombre: str
    direccion: str
    telefono: str
    ciudad: str
    categoria_busqueda: str  # keyword solicitada
    url_raw: str             # URL de la ficha en la fuente original
    fuente: str              # "google_maps", "deperu", etc.

    # === DATOS COMUNES OPCIONALES ===
    email: Optional[str] = None
    website: Optional[str] = None
    distrito: Optional[str] = None
    provincia: Optional[str] = None
    region: Optional[str] = None
    categoria_fuente: Optional[str] = None
    maps_url: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    precio: Optional[str] = None

    # === METADATOS ===
    scraped_at: datetime = field(default_factory=datetime.now)
    job_id: str = ""
    categoria_pred: Optional[str] = None  # ML
    confianza: Optional[float] = None     # ML (0-1)
    nombre_norm: Optional[str] = None    # nombre normalizado (uso interno del pipeline V2)
    calidad: Optional[str] = None        # calidad del lead (uso interno del pipeline V2)

    # === DATOS ESPECIFICOS DE FUENTE (no tocan el modelo) ===
    raw_fields: dict = field(default_factory=dict)
    # Ej: {"google_maps": {"business_id": "...", "abierto": True},
    #      "deperu": {"ruc": "20123456789", "giro_comercial": "Ferreteria"}}

    # === ATRIBUTION POR CAMPO (para enriquecimiento) ===
    field_sources: dict = field(default_factory=dict)
    # Ej: {"telefono": "google_maps", "email": "deperu", "website": "google_maps"}

    # Campos comunes del negocio para enriquecimiento
    COMMON_FIELDS: ClassVar[list] = [
        "nombre", "direccion", "telefono", "ciudad", "categoria_busqueda",
        "email", "website", "distrito", "provincia", "region",
        "categoria_fuente", "maps_url", "latitud", "longitud",
        "rating", "reviews_count", "precio",
    ]

    def to_dict(self) -> dict:
        """Serializa a dict para JSON API.

        El scraped_at se serializa como ISO string para compatibilidad JSON.
        """
        return {
            "nombre": self.nombre,
            "direccion": self.direccion,
            "telefono": self.telefono,
            "ciudad": self.ciudad,
            "categoria_busqueda": self.categoria_busqueda,
            "url_raw": self.url_raw,
            "fuente": self.fuente,
            "email": self.email,
            "website": self.website,
            "distrito": self.distrito,
            "provincia": self.provincia,
            "region": self.region,
            "categoria_fuente": self.categoria_fuente,
            "maps_url": self.maps_url,
            "latitud": self.latitud,
            "longitud": self.longitud,
            "rating": self.rating,
            "reviews_count": self.reviews_count,
            "precio": self.precio,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "job_id": self.job_id,
            "categoria_pred": self.categoria_pred,
            "confianza": self.confianza,
            "nombre_norm": self.nombre_norm,
            "calidad": self.calidad,
            "raw_fields": self.raw_fields,
            "field_sources": self.field_sources,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Lead":
        """Deserializa desde dict.

        Acepta scraped_at como string ISO o como datetime.
        Los campos opcionales que falten toman valor por defecto.
        """
        # Campos requeridos — nunca deben faltar
        kwargs = {
            "nombre": data.get("nombre", ""),
            "direccion": data.get("direccion", ""),
            "telefono": data.get("telefono", ""),
            "ciudad": data.get("ciudad", ""),
            "categoria_busqueda": data.get("categoria_busqueda", ""),
            "url_raw": data.get("url_raw", ""),
            "fuente": data.get("fuente", ""),
        }
        # Campos opcionales — copiar si existen
        optional_fields = [
            "email", "website", "distrito", "provincia", "region",
            "categoria_fuente", "maps_url", "latitud", "longitud",
            "rating", "reviews_count", "precio", "scraped_at",
            "job_id", "categoria_pred", "confianza", "nombre_norm", "calidad",
            "raw_fields", "field_sources",
        ]
        for k in optional_fields:
            if k in data and data[k] is not None:
                kwargs[k] = data[k]
        # scraped_at puede venir como string ISO
        if "scraped_at" in kwargs and isinstance(kwargs["scraped_at"], str):
            try:
                kwargs["scraped_at"] = datetime.fromisoformat(kwargs["scraped_at"])
            except (ValueError, TypeError):
                kwargs["scraped_at"] = datetime.now()
        return cls(**kwargs)
