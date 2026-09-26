"""Tests de integracion API: jobs y cancelacion por job_id.

Verifica:
  1. /api/scrape devuelve job_id
  2. job_id es UUID valido
  3. /api/cancel recibe job_id y cancela ese job
  4. Cancelar A no cancela B (aislamiento)
  5. Job inexistente -> 404 controlado
  6. Estados finales correctos
  7. Respuesta Legacy de /api/scrape sigue funcionando
  8. Integracion no rompe adapter leads_a_dict_legacy
"""
import threading
import pytest
from unittest.mock import AsyncMock, patch


SAMPLE_RAW = [
    {
        "nombre": "Clínica Dental Madrid",
        "direccion": "Calle Mayor 10, Madrid",
        "telefono": "+34 912 345 678",
        "ciudad": "Madrid",
        "categoria": "Dentistas",
        "maps_url": "https://maps.google.com/place/abc123",
        "categoria_pred": "salud",
        "confianza": 0.95,
    },
    {
        "nombre": "Dentistas López",
        "direccion": "Av. de la Constitución 25, Madrid",
        "telefono": "+34 911 234 567",
        "ciudad": "Madrid",
        "categoria": "Dentistas",
        "maps_url": "https://maps.google.com/place/def456",
        "categoria_pred": "salud",
        "confianza": 0.90,
    },
]


def _dict_to_lead(d):
    from modelos.lead import Lead
    return Lead(
        nombre=d.get("nombre", ""),
        direccion=d.get("direccion", ""),
        telefono=d.get("telefono", ""),
        ciudad=d.get("ciudad", ""),
        categoria_busqueda=d.get("categoria", ""),
        url_raw=d.get("maps_url", ""),
        fuente="google_maps",
        maps_url=d.get("maps_url", ""),
        categoria_pred=d.get("categoria_pred"),
        confianza=d.get("confianza"),
        job_id="",
    )


SAMPLE_LEADS = [_dict_to_lead(d) for d in SAMPLE_RAW]


# --- Tests /api/scrape con job_id ---

def test_scrape_devuelve_job_id(client):
    """POST /api/scrape devuelve job_id en la respuesta."""
    with patch("fuentes.google_maps.GoogleMapsSource.scrape", return_value=SAMPLE_LEADS):
        resp = client.post("/api/scrape", json={
            "keyword": "Dentistas", "city": "Madrid", "limit": 10
        })

    assert resp.status_code == 200
    data = resp.get_json()
    assert "job_id" in data
    assert data["job_id"] is not None
    assert isinstance(data["job_id"], str)
    assert len(data["job_id"]) == 36


def test_scrape_job_id_es_uuid_valido(client):
    """job_id devuelto es un UUID v4 valido."""
    import uuid
    with patch("fuentes.google_maps.GoogleMapsSource.scrape", return_value=SAMPLE_LEADS):
        resp = client.post("/api/scrape", json={
            "keyword": "Dentistas", "city": "Madrid", "limit": 10
        })

    data = resp.get_json()
    job_id = data["job_id"]
    # Validar que es UUID v4
    parsed = uuid.UUID(job_id)
    assert parsed.version == 4


def test_scrape_respuesta_legacy_intacta(client):
    """La respuesta legacy (success, data[]) se mantiene intacta."""
    with patch("fuentes.google_maps.GoogleMapsSource.scrape", return_value=SAMPLE_LEADS):
        resp = client.post("/api/scrape", json={
            "keyword": "Dentistas", "city": "Madrid", "limit": 10
        })

    data = resp.get_json()
    assert data["success"] is True
    assert "data" in data
    assert len(data["data"]) == 2
    assert data["data"][0]["nombre"] == "Clínica Dental Madrid"
    assert "categoria" in data["data"][0]
    assert "categoria_busqueda" not in data["data"][0]


def test_scrape_campos_legacy_en_data(client):
    """Todos los 8 campos legacy estan presentes en cada lead."""
    with patch("fuentes.google_maps.GoogleMapsSource.scrape", return_value=SAMPLE_LEADS):
        resp = client.post("/api/scrape", json={
            "keyword": "Dentistas", "city": "Madrid", "limit": 10
        })

    data = resp.get_json()
    expected_keys = {
        "nombre", "direccion", "telefono", "ciudad",
        "categoria", "maps_url", "categoria_pred", "confianza",
    }
    for item in data["data"]:
        assert set(item.keys()) == expected_keys


def test_scrape_cancelled_flag_false_por_defecto(client):
    """cancelled es False por defecto (no se cancelo)."""
    with patch("fuentes.google_maps.GoogleMapsSource.scrape", return_value=SAMPLE_LEADS):
        resp = client.post("/api/scrape", json={
            "keyword": "Dentistas", "city": "Madrid", "limit": 10
        })

    data = resp.get_json()
    assert "cancelled" in data
    assert data["cancelled"] is False


# --- Tests /api/cancel con job_id ---

def test_cancel_recibe_job_id_y_cancela(client):
    """POST /api/cancel con job_id cancela ese job."""
    with patch("fuentes.google_maps.GoogleMapsSource.scrape", return_value=SAMPLE_LEADS):
        resp = client.post("/api/scrape", json={
            "keyword": "Dentistas", "city": "Madrid", "limit": 10
        })
    job_id = resp.get_json()["job_id"]

    cancel_resp = client.post("/api/cancel", json={"job_id": job_id})
    assert cancel_resp.status_code == 200
    cancel_data = cancel_resp.get_json()
    assert cancel_data["success"] is True
    assert cancel_data["job_id"] == job_id


def test_cancel_job_inexistente_devuelve_404(client):
    """Cancelar job inexistente devuelve 404."""
    resp = client.post("/api/cancel", json={"job_id": "00000000-0000-0000-0000-000000000000"})
    assert resp.status_code == 404
    data = resp.get_json()
    assert "error" in data
    assert "no encontrado" in data["error"].lower()


def test_cancel_sin_job_id_devuelve_400(client):
    """Cancelar sin job_id devuelve 400."""
    resp = client.post("/api/cancel", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


# --- Tests aislamiento concurrente ---

def test_cancelar_a_no_cancela_b(client):
    """Cancelar job A no afecta job B (aislamiento)."""
    # Crear job A
    with patch("fuentes.google_maps.GoogleMapsSource.scrape", return_value=SAMPLE_LEADS):
        resp_a = client.post("/api/scrape", json={
            "keyword": "Dentistas", "city": "Madrid", "limit": 10
        })
    job_id_a = resp_a.get_json()["job_id"]

    # Crear job B
    with patch("fuentes.google_maps.GoogleMapsSource.scrape", return_value=SAMPLE_LEADS):
        resp_b = client.post("/api/scrape", json={
            "keyword": "Cafeterias", "city": "Barcelona", "limit": 10
        })
    job_id_b = resp_b.get_json()["job_id"]

    assert job_id_a != job_id_b

    # Cancelar A
    cancel_resp = client.post("/api/cancel", json={"job_id": job_id_a})
    assert cancel_resp.status_code == 200

    # Verificar que A esta cancelado
    from app import gestor_jobs
    from servicios.gestor_jobs import EstadoJob
    estado_a = gestor_jobs.obtener_estado(job_id_a)
    assert estado_a["estado"] == EstadoJob.CANCELLED

    # Verificar que B NO esta cancelado (sigue PENDING o RUNNING)
    estado_b = gestor_jobs.obtener_estado(job_id_b)
    assert estado_b["estado"] != EstadoJob.CANCELLED
    assert estado_b["estado"] in (EstadoJob.PENDING, EstadoJob.RUNNING, EstadoJob.COMPLETED, EstadoJob.FAILED)


# --- Tests estados finales ---

def test_scrape_estado_completed_al_finalizar(client):
    """Job pasa a COMPLETED al finalizar con exito."""
    with patch("fuentes.google_maps.GoogleMapsSource.scrape", return_value=SAMPLE_LEADS):
        resp = client.post("/api/scrape", json={
            "keyword": "Dentistas", "city": "Madrid", "limit": 10
        })
    job_id = resp.get_json()["job_id"]

    from app import gestor_jobs
    from servicios.gestor_jobs import EstadoJob
    estado = gestor_jobs.obtener_estado(job_id)
    assert estado["estado"] == EstadoJob.COMPLETED


def test_scrape_estado_failed_en_error(client):
    """Job pasa a FAILED si hay error en scraping."""
    async def raise_error(request, cancel_event=None):
        from excepciones.source_errors import SourceError
        raise SourceError("google_maps", "Error de prueba", retryable=False)

    with patch("app.Orquestador") as MockOrquestador:
        instance = MockOrquestador.return_value
        instance.orquestar = AsyncMock(side_effect=raise_error)
        resp = client.post("/api/scrape", json={
            "keyword": "Test", "city": "Madrid", "limit": 10
        })

    assert resp.status_code == 502
    job_id = resp.get_json()["job_id"]

    from app import gestor_jobs
    from servicios.gestor_jobs import EstadoJob
    estado = gestor_jobs.obtener_estado(job_id)
    assert estado["estado"] == EstadoJob.FAILED
    assert "Error de prueba" in estado["error"]


def test_scrape_estado_cancelled_si_cancelado_durante_ejecucion(client):
    """Job pasa a CANCELLED si se cancela durante ejecucion.

    Usa sincronizacion determinista con threading.Event para evitar
    threads residuales y race conditions.
    """
    import time
    import threading
    from unittest.mock import AsyncMock, patch

    # Eventos de sincronizacion
    scrape_started = threading.Event()  # Señala que el scraping esta en ejecucion
    allow_proceed = threading.Event()   # Permite que el scraping continue/termine
    scrape_finished = threading.Event() # Señala que el scraping termino

    async def controlled_scrape(request, cancel_event=None):
        """Scraping controlado que se bloquea hasta que el test lo permita."""
        # Señalar que el scraping ha empezado
        scrape_started.set()

        # Esperar a que el test permita continuar (o que se cancele)
        # Usamos wait con timeout corto para poder responder a cancel_event
        while not allow_proceed.is_set():
            if cancel_event is not None and cancel_event.is_set():
                scrape_finished.set()
                return SAMPLE_LEADS  # Retorno controlado al ser cancelado
            await asyncio.sleep(0.01)

        scrape_finished.set()
        return SAMPLE_LEADS

    import asyncio
    with patch("app.Orquestador") as MockOrquestador:
        instance = MockOrquestador.return_value
        instance.orquestar = AsyncMock(side_effect=controlled_scrape)

        # Lanzar scraping en background
        result_container = {}

        def do_scrape():
            try:
                resp = client.post("/api/scrape", json={
                    "keyword": "Test", "city": "Madrid", "limit": 10
                })
                result_container["resp"] = resp
            except Exception as e:
                result_container["error"] = e
            finally:
                scrape_finished.set()  # Asegurar señal de fin

        t = threading.Thread(target=do_scrape)
        t.start()

        # Esperar a que el scraping haya empezado (job creado y en RUNNING)
        assert scrape_started.wait(timeout=5), "El scraping no inicio a tiempo"

        # Buscar job_id recien creado - usar obtener_estado para thread-safety
        from app import gestor_jobs
        from servicios.gestor_jobs import EstadoJob
        job_id = None
        for attempt in range(100):
            for jid in list(gestor_jobs._jobs.keys()):
                estado = gestor_jobs.obtener_estado(jid)
                if estado and estado["estado"] in (EstadoJob.PENDING, EstadoJob.RUNNING):
                    job_id = jid
                    break
            if job_id:
                break
            time.sleep(0.01)

        assert job_id is not None, "No se encontro job_id en ejecucion"

        # Cancelar el job
        cancel_resp = client.post("/api/cancel", json={"job_id": job_id})
        assert cancel_resp.status_code == 200

        # Permitir que el scraping termine limpiamente (respondera al cancel_event)
        allow_proceed.set()

        # Esperar a que el thread termine
        assert scrape_finished.wait(timeout=5), "El scraping no termino tras cancelacion"
        t.join(timeout=5)
        assert not t.is_alive(), "Thread residual detectado"

# Verificar estado final
        estado = gestor_jobs.obtener_estado(job_id)
        assert estado["estado"] == EstadoJob.CANCELLED


# --- Tests compatibilidad ---

def test_scrape_error_incluye_job_id(client):
    """Respuestas de error incluyen job_id."""
    async def raise_error(request, cancel_event=None):
        from excepciones.source_errors import SourceError
        raise SourceError("google_maps", "Error de prueba", retryable=False)

    with patch("app.Orquestador") as MockOrquestador:
        instance = MockOrquestador.return_value
        instance.orquestar = AsyncMock(side_effect=raise_error)
        resp = client.post("/api/scrape", json={
            "keyword": "Test", "city": "Madrid", "limit": 10
        })

    assert resp.status_code == 502
    data = resp.get_json()
    assert "job_id" in data
    assert data["job_id"] is not None


def test_adapter_leads_a_dict_legacy_sigue_funcionando(client):
    """El adapter leads_a_dict_legacy no se rompe con la integracion."""
    from servicios.response_adapter import leads_a_dict_legacy
    from modelos.lead import Lead

    lead = Lead(
        nombre="Test",
        direccion="Dir",
        telefono="123",
        ciudad="Madrid",
        categoria_busqueda="Test",
        url_raw="url",
        fuente="google_maps",
        maps_url="url",
        categoria_pred="pred",
        confianza=0.9,
        job_id="job-123",
    )

    result = leads_a_dict_legacy([lead])
    assert len(result) == 1
    assert result[0]["nombre"] == "Test"
    assert result[0]["categoria"] == "Test"
    assert "categoria_busqueda" not in result[0]


def test_multiple_scrape_requests_crean_jobs_distintos(client):
    """Multiples requests crean jobs con IDs distintos."""
    with patch("fuentes.google_maps.GoogleMapsSource.scrape", return_value=SAMPLE_LEADS):
        resp1 = client.post("/api/scrape", json={"keyword": "A", "city": "Madrid", "limit": 10})
        resp2 = client.post("/api/scrape", json={"keyword": "B", "city": "Madrid", "limit": 10})

    job_id_1 = resp1.get_json()["job_id"]
    job_id_2 = resp2.get_json()["job_id"]

    assert job_id_1 != job_id_2


# Necesario para test de cancelacion concurrente
import asyncio
