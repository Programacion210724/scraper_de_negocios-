"""Gestor de jobs en memoria — gestion de job_id y cancel tokens.

Implementacion MINIMAL en memoria para Fase 2:
  - job_id (UUID4)
  - estado (pending/running/completed/failed/cancelled)
  - cancel_event (threading.Event por job)

NO usa base de datos, colas, Redis ni persistencia.
Eso llega en Fase 3 con persistencia/job_repository.py.
"""
import logging
import threading
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from modelos.scrape_request import ScrapeRequest

logger = logging.getLogger(__name__)


class EstadoJob(Enum):
    """Estados posibles de un job de scraping."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GestorJobs:
    """Gestor minimal de jobs en memoria.

    Administra job_id, estado y cancel tokens.
    Cada job se identifica con un UUID4 generado por crear_job().
    """

    def __init__(self):
        self._jobs: Dict[str, dict] = {}

    def crear_job(self, request: ScrapeRequest) -> str:
        """Crea un nuevo job y retorna el job_id.

        Args:
            request: ScrapeRequest con los parametros de scraping.

        Returns:
            str: UUID4 del job creado.
        """
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = {
            "job_id": job_id,
            "estado": EstadoJob.PENDING,
            "cancel_event": threading.Event(),
            "created_at": datetime.now().isoformat(),
            "source": request.source,
            "keyword": request.keyword,
            "city": request.city,
            "limit": request.limit,
            "mode": request.mode,
            "error": None,
            "total_found": 0,
            "total_unique": 0,
        }
        logger.info(
            "Job creado: job_id=%s source=%s keyword=%s city=%s",
            job_id, request.source, request.keyword, request.city,
        )
        return job_id

    def obtener_estado(self, job_id: str) -> Optional[dict]:
        """Retorna el estado del job, o None si no existe."""
        return self._jobs.get(job_id)

    def actualizar_estado(self, job_id: str, estado: EstadoJob) -> bool:
        """Actualiza el estado del job.

        Returns:
            True si el job existe y se actualizo, False si no existe.
        """
        if job_id not in self._jobs:
            logger.warning("Job no encontrado: %s", job_id)
            return False
        self._jobs[job_id]["estado"] = estado
        logger.info("Job %s actualizado a estado: %s", job_id, estado.value)
        return True

    def obtener_cancel_event(self, job_id: str) -> Optional[threading.Event]:
        """Obtiene el cancel_event del job para pasarlo al orquestador."""
        job = self._jobs.get(job_id)
        if job:
            return job["cancel_event"]
        return None

    def cancelar_job(self, job_id: str) -> bool:
        """Cancela un job activo, marcandolo como CANCELLED."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        job["cancel_event"].set()
        job["estado"] = EstadoJob.CANCELLED
        logger.info("Job cancelado: job_id=%s", job_id)
        return True

    def registrar_resultados(self, job_id: str, total_found: int, total_unique: int) -> None:
        """Registra estadisticas del job completado."""
        if job_id in self._jobs:
            self._jobs[job_id]["total_found"] = total_found
            self._jobs[job_id]["total_unique"] = total_unique
            self._jobs[job_id]["estado"] = EstadoJob.COMPLETED
            logger.info(
                "Job %s completado: %d found, %d unique",
                job_id, total_found, total_unique,
            )

    def registrar_error(self, job_id: str, error: str) -> None:
        """Registra un error en el job."""
        if job_id in self._jobs:
            self._jobs[job_id]["estado"] = EstadoJob.FAILED
            self._jobs[job_id]["error"] = error
            logger.error("Job %s fallo: %s", job_id, error)
