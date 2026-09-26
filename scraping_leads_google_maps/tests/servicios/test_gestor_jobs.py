"""Tests unitarios de GestorJobs.

Verifica:
  - crear_job genera UUID valido
  - obtener_estado retorna job
  - actualizar_estado cambia estado
  - obtener_cancel_event retorna threading.Event
  - cancelar_job marca CANCELLED y setea event
  - registrar_resultados guarda stats y pone COMPLETED
  - registrar_error pone FAILED y guarda error
  - aislamiento: jobs independientes no se afectan
  - thread-safety basico con RLock
"""
import threading
import pytest
from concurrent.futures import ThreadPoolExecutor

from modelos.scrape_request import ScrapeRequest
from servicios.gestor_jobs import GestorJobs, EstadoJob


@pytest.fixture
def gestor():
    return GestorJobs()


@pytest.fixture
def sample_request():
    return ScrapeRequest(
        keyword="Dentistas",
        city="Madrid",
        limit=10,
        mode="simple",
        source="google_maps",
    )


def test_crear_job_retorna_uuid(gestor, sample_request):
    job_id = gestor.crear_job(sample_request)
    assert job_id is not None
    assert isinstance(job_id, str)
    assert len(job_id) == 36


def test_crear_job_estado_pending(gestor, sample_request):
    job_id = gestor.crear_job(sample_request)
    estado = gestor.obtener_estado(job_id)
    assert estado is not None
    assert estado["estado"] == EstadoJob.PENDING


def test_obtener_estado_job_existente(gestor, sample_request):
    job_id = gestor.crear_job(sample_request)
    estado = gestor.obtener_estado(job_id)
    assert estado["job_id"] == job_id
    assert estado["keyword"] == "Dentistas"
    assert estado["city"] == "Madrid"
    assert estado["limit"] == 10
    assert estado["mode"] == "simple"
    assert estado["source"] == "google_maps"


def test_obtener_estado_job_inexistente(gestor):
    estado = gestor.obtener_estado("job-inexistente")
    assert estado is None


def test_actualizar_estado_job_existente(gestor, sample_request):
    job_id = gestor.crear_job(sample_request)
    result = gestor.actualizar_estado(job_id, EstadoJob.RUNNING)
    assert result is True
    estado = gestor.obtener_estado(job_id)
    assert estado["estado"] == EstadoJob.RUNNING


def test_actualizar_estado_job_inexistente(gestor):
    result = gestor.actualizar_estado("job-inexistente", EstadoJob.RUNNING)
    assert result is False


def test_obtener_cancel_event_job_existente(gestor, sample_request):
    job_id = gestor.crear_job(sample_request)
    event = gestor.obtener_cancel_event(job_id)
    assert event is not None
    assert isinstance(event, threading.Event)
    assert not event.is_set()


def test_obtener_cancel_event_job_inexistente(gestor):
    event = gestor.obtener_cancel_event("job-inexistente")
    assert event is None


def test_cancelar_job_job_existente(gestor, sample_request):
    job_id = gestor.crear_job(sample_request)
    event = gestor.obtener_cancel_event(job_id)
    assert not event.is_set()

    result = gestor.cancelar_job(job_id)
    assert result is True

    event_after = gestor.obtener_cancel_event(job_id)
    assert event_after.is_set()

    estado = gestor.obtener_estado(job_id)
    assert estado["estado"] == EstadoJob.CANCELLED


def test_cancelar_job_job_inexistente(gestor):
    result = gestor.cancelar_job("job-inexistente")
    assert result is False


def test_registrar_resultados(gestor, sample_request):
    job_id = gestor.crear_job(sample_request)
    gestor.registrar_resultados(job_id, total_found=100, total_unique=50)

    estado = gestor.obtener_estado(job_id)
    assert estado["estado"] == EstadoJob.COMPLETED
    assert estado["total_found"] == 100
    assert estado["total_unique"] == 50


def test_registrar_error(gestor, sample_request):
    job_id = gestor.crear_job(sample_request)
    gestor.registrar_error(job_id, "Error de prueba")

    estado = gestor.obtener_estado(job_id)
    assert estado["estado"] == EstadoJob.FAILED
    assert estado["error"] == "Error de prueba"


def test_aislamiento_entre_jobs(gestor):
    req1 = ScrapeRequest(keyword="A", city="Madrid", limit=10, mode="simple", source="google_maps")
    req2 = ScrapeRequest(keyword="B", city="Barcelona", limit=20, mode="deep", source="google_maps")

    job_id_1 = gestor.crear_job(req1)
    job_id_2 = gestor.crear_job(req2)

    assert job_id_1 != job_id_2

    gestor.actualizar_estado(job_id_1, EstadoJob.RUNNING)
    gestor.cancelar_job(job_id_2)

    estado_1 = gestor.obtener_estado(job_id_1)
    estado_2 = gestor.obtener_estado(job_id_2)

    assert estado_1["estado"] == EstadoJob.RUNNING
    assert estado_2["estado"] == EstadoJob.CANCELLED
    assert estado_1["keyword"] == "A"
    assert estado_2["keyword"] == "B"


def test_thread_safety_crear_jobs_concurrentes(gestor):
    """Verifica que crear_job es thread-safe bajo concurrencia."""
    num_threads = 10
    jobs_creados = []

    def crear_job_worker(i):
        req = ScrapeRequest(
            keyword=f"Test{i}",
            city="Ciudad",
            limit=10,
            mode="simple",
            source="google_maps",
        )
        job_id = gestor.crear_job(req)
        jobs_creados.append(job_id)

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(crear_job_worker, i) for i in range(num_threads)]
        for f in futures:
            f.result()

    assert len(jobs_creados) == num_threads
    assert len(set(jobs_creados)) == num_threads

    for job_id in jobs_creados:
        estado = gestor.obtener_estado(job_id)
        assert estado is not None
        assert estado["estado"] == EstadoJob.PENDING


def test_thread_safety_cancelar_jobs_concurrentes(gestor):
    """Verifica que cancelar_job es thread-safe bajo concurrencia."""
    num_jobs = 20
    job_ids = []

    for i in range(num_jobs):
        req = ScrapeRequest(keyword=f"Test{i}", city="Ciudad", limit=10, mode="simple", source="google_maps")
        job_ids.append(gestor.crear_job(req))

    def cancelar_worker(job_id):
        return gestor.cancelar_job(job_id)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(cancelar_worker, jid) for jid in job_ids]
        results = [f.result() for f in futures]

    assert all(results)

    for job_id in job_ids:
        estado = gestor.obtener_estado(job_id)
        assert estado["estado"] == EstadoJob.CANCELLED
        assert gestor.obtener_cancel_event(job_id).is_set()


def test_job_contiene_campos_esperados(gestor, sample_request):
    job_id = gestor.crear_job(sample_request)
    estado = gestor.obtener_estado(job_id)

    expected_keys = {
        "job_id", "estado", "cancel_event", "created_at",
        "source", "keyword", "city", "limit", "mode",
        "error", "total_found", "total_unique",
    }
    assert set(estado.keys()) == expected_keys


def test_multiples_actualizaciones_estado(gestor, sample_request):
    job_id = gestor.crear_job(sample_request)

    gestor.actualizar_estado(job_id, EstadoJob.RUNNING)
    assert gestor.obtener_estado(job_id)["estado"] == EstadoJob.RUNNING

    gestor.actualizar_estado(job_id, EstadoJob.COMPLETED)
    assert gestor.obtener_estado(job_id)["estado"] == EstadoJob.COMPLETED

    gestor.actualizar_estado(job_id, EstadoJob.FAILED)
    assert gestor.obtener_estado(job_id)["estado"] == EstadoJob.FAILED


def test_cancel_event_es_unico_por_job(gestor):
    req1 = ScrapeRequest(keyword="A", city="Madrid", limit=10, mode="simple", source="google_maps")
    req2 = ScrapeRequest(keyword="B", city="Barcelona", limit=10, mode="simple", source="google_maps")

    job_id_1 = gestor.crear_job(req1)
    job_id_2 = gestor.crear_job(req2)

    event_1 = gestor.obtener_cancel_event(job_id_1)
    event_2 = gestor.obtener_cancel_event(job_id_2)

    assert event_1 is not event_2
    assert not event_1.is_set()
    assert not event_2.is_set()

    event_1.set()
    assert event_1.is_set()
    assert not event_2.is_set()