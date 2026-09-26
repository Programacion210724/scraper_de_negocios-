from flask import Flask, render_template, request, jsonify, send_file
import asyncio
import threading
import pandas as pd
import io
import logging
import os

import fuentes  # noqa: F401 — activa el registro de GoogleMapsSource en ScraperFactory
from modelos.scrape_request import ScrapeRequest
from servicios.orquestador import Orquestador
from servicios.response_adapter import leads_a_dict_legacy
from servicios.gestor_jobs import GestorJobs, EstadoJob
from excepciones.source_errors import SourceError, CaptchaError, SourceTimeoutError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
gestor_jobs = GestorJobs()
DEFAULT_SHEET_ID = os.environ.get('DEFAULT_SHEET_ID', '1Vpal9WMVimSpIMf6-eljk-vQW3LyNB41z9KcRV45jQI')

@app.route('/api/save-to-sheets', methods=['POST'])
def save_to_sheets():
    data = request.get_json()
    if not data or 'results' not in data or not data['results']:
        return jsonify({'error': 'No hay datos para guardar'}), 400

    sheet_id = data.get('sheet_id') or DEFAULT_SHEET_ID
    if not sheet_id:
        return jsonify({'error': 'ID de hoja no especificado. Configure DEFAULT_SHEET_ID o envíelo en la solicitud'}), 400

    headers = ['Nombre', 'Dirección', 'Teléfono', 'Ciudad', 'Categoría', 'Google Maps']
    rows = [headers] + [
        [
            r.get('nombre', ''),
            r.get('direccion', ''),
            r.get('telefono', ''),
            r.get('ciudad', ''),
            r.get('categoria', ''),
            r.get('maps_url', '')
        ] for r in data['results']
    ]

    try:
        from google_sheets import append_rows
        append_rows(sheet_id, rows)
        return jsonify({'success': True, 'message': 'Datos guardados en Google Sheets'})
    except Exception as e:
        logger.exception("Error al guardar en Sheets")
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/scrape', methods=['POST'])
def scrape():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No se recibió información en la solicitud'}), 400

    keyword = data.get('keyword')
    city = data.get('city')
    mode = data.get('mode', 'simple')
    try:
        limit_raw = data.get('limit', 20)
        limit = int(limit_raw)
        if limit <= 0: raise ValueError("El límite debe ser mayor a 0")
        if limit > 100: limit = 100
    except (ValueError, TypeError):
        return jsonify({'error': 'El límite debe ser un número entero válido'}), 400

    if not keyword or not city:
        return jsonify({'error': 'La palabra clave y la ciudad son obligatorias'}), 400

    logger.info(f"Iniciando scraping ({mode}): '{keyword}' en '{city}' (Límite: {limit})")

    orquestador = Orquestador()
    scrape_request = ScrapeRequest(
        keyword=keyword,
        city=city,
        limit=limit,
        mode=mode,
    )

    job_id = gestor_jobs.crear_job(scrape_request)
    cancel_event = gestor_jobs.obtener_cancel_event(job_id)
    gestor_jobs.actualizar_estado(job_id, EstadoJob.RUNNING)

    try:
        leads = asyncio.run(asyncio.wait_for(
            orquestador.orquestar(scrape_request, cancel_event),
            timeout=600.0
        ))
        if leads is None:
            gestor_jobs.registrar_error(job_id, 'El proceso de scraping no devolvió resultados')
            return jsonify({'error': 'El proceso de scraping no devolvió resultados', 'job_id': job_id}), 500
        if cancel_event.is_set():
            gestor_jobs.actualizar_estado(job_id, EstadoJob.CANCELLED)
            return jsonify({'success': True, 'data': leads_a_dict_legacy(leads), 'cancelled': True, 'job_id': job_id})
        gestor_jobs.registrar_resultados(job_id, len(leads), len(leads))
        return jsonify({'success': True, 'data': leads_a_dict_legacy(leads), 'cancelled': False, 'job_id': job_id})
    except asyncio.TimeoutError:
        gestor_jobs.registrar_error(job_id, 'Timeout: la solicitud tardó demasiado')
        return jsonify({'error': 'La solicitud tardó demasiado. Intente con un límite menor o modo simple.', 'job_id': job_id}), 504
    except SourceTimeoutError as e:
        logger.warning(
            "Technical summary: timeout in source %s | Resumen: timeout en %s. Reintentalo.",
            e.source, e.source,
        )
        gestor_jobs.registrar_error(job_id, f'Timeout en la fuente {e.source}')
        return jsonify({'error': f'Timeout en la fuente {e.source}. Intente más tarde.', 'job_id': job_id}), 504
    except CaptchaError as e:
        logger.warning(
            "Technical summary: captcha detected in source %s | Resumen: captcha en %s.",
            e.source, e.source,
        )
        gestor_jobs.registrar_error(job_id, f'Captcha detectado en {e.source}')
        return jsonify({'error': f'Captcha detectado en {e.source}. Intente más tarde.', 'job_id': job_id}), 503
    except SourceError as e:
        logger.error(
            "Technical summary: source error from %s | Resumen: error en la fuente %s. Reintenta.",
            e.source, e.source,
        )
        gestor_jobs.registrar_error(job_id, f'Error en la fuente {e.source}: {e.message}')
        return jsonify({'error': f'Error en la fuente {e.source}: {e.message}', 'job_id': job_id}), 502
    except Exception as e:
        logger.exception(f"Error inesperado: {str(e)}")
        gestor_jobs.registrar_error(job_id, f"Error interno del servidor: {str(e)}")
        return jsonify({'error': f"Error interno del servidor: {str(e)}", 'job_id': job_id}), 500

@app.route('/api/cancel', methods=['POST'])
def cancel():
    data = request.get_json()
    if not data or 'job_id' not in data:
        return jsonify({'error': 'job_id es obligatorio'}), 400

    job_id = data['job_id']
    success = gestor_jobs.cancelar_job(job_id)
    if not success:
        return jsonify({'error': f'Job no encontrado: {job_id}'}), 404
    return jsonify({'success': True, 'message': 'Job cancelado', 'job_id': job_id})

@app.route('/api/download', methods=['POST'])
def download():
    data = request.get_json()
    if not data or 'results' not in data or not data['results']:
        return jsonify({'error': 'No hay datos disponibles para descargar'}), 400
    try:
        df = pd.DataFrame(data['results'])
        if df.empty: return jsonify({'error': 'Los datos están vacíos'}), 400
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Leads')
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='leads_google_maps.xlsx')
    except Exception as e:
        logger.exception(f"Error al generar Excel: {str(e)}")
        return jsonify({'error': 'Error al generar el archivo de descarga'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)