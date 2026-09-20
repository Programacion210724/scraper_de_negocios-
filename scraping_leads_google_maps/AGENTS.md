# AGENTS.md — Reglas del proyecto scraping_leads_google_maps

Este archivo define las reglas obligatorias del proyecto. Cualquier agente o
herramienta (opencode, Claude Code, Cursor, Kilo Code, etc.) debe respetarlas.

## 1. Arquitectura por capas y nivel de protección

scraping_leads_google_maps/
├── scraper/          NIVEL A — Legacy Core (solo leer; extender via adapters)
│   ├── scraper.py      scrape_google_maps() + lote/sesión + dedup + ML filter
│   ├── classifier.py   Modelo ML (TF-IDF + Logistic Regression)
│   ├── proxy.py        Proxy HTTP (puertos dinámicos)
│   └── debug/          Artefactos de depuración (ignorado por git)
├── modelos/          NIVEL B — V2 Arquitectura crítica (modificar con análisis)
│   ├── lead.py         Lead dataclass (contrato multi-source)
│   ├── scrape_request.py  ScrapeRequest (params unificados)
│   └── source_config.py   SourceConfig (priority, country, requires_proxy)
├── fuentes/          V2 — Fuentes/adapters (base.py es Nivel B)
│   ├── base.py         NIVEL B — ScraperInterface (ABC, contrato compartido)
│   ├── google_maps.py  NIVEL C — Adapter: legacy → Lead[]
│   └── __init__.py     NIVEL C — Registro en ScraperFactory
├── servicios/        NIVEL C — V2 Servicios/pipeline (orquestador y factory son B)
│   ├── orquestador.py  NIVEL B — Pipeline completo V2
│   ├── fabrica_scrapers.py  NIVEL B — ScraperFactory (registry pattern)
│   ├── clasificador_servicio.py  NIVEL C — Wrapper read-only del core classifier
│   ├── normalizador.py  NIVEL C — Normaliza campos (delega al core)
│   ├── validador.py     NIVEL C — Valida leads (nombre obligatorio)
│   ├── deduplicator.py  NIVEL C — L1/L2/L3 deduplicación
│   ├── enriquecedor.py  NIVEL C — Merge cross-source
│   └── gestor_jobs.py   NIVEL C — Job registry en memoria
├── excepciones/      NIVEL C — Excepciones de dominio (extensible)
│   ├── source_errors.py  SourceError, CaptchaError, SourceTimeoutError
│   └── validation_errors.py  ValidationError, InvalidLeadError
├── api/              NIVEL C — Futuro: REST API V2 (async Flask)
├── persistencia/     NIVEL C — Futuro: BD layer (Fase 3+)
├── exportadores/     NIVEL C — Futuro: Excel, PDF, CSV (Fase 3+)
├── tests/            Pruebas (pytest + pytest-asyncio)
├── docker/           NIVEL C — Docker (Dockerfile, compose)
├── static/           NIVEL C — Recursos frontend (CSS/JS)
├── templates/        NIVEL C — Plantillas HTML (legacy + evolutivas)
├── requirements.txt  Dependencias
└── README.md         Documentación

PRINCIPIOS:
  - Legacy Core (Nivel A): NUNCA modificar. Proveer funcionalidad vía adapters.
  - V2 Arquitectura (Nivel B): Contrato/contract estable. Cambios requieren análisis.
  - V2 Componentes (Nivel C): Evolutivos. Modificar/libres con tests.
  - Frontend (static/, templates/): Nivel C. Preservar compatibilidad visual
    y funcional con el frontend legacy existente.

## 2. Archivos protegidos por nivel

NIVEL A — Legacy Core protegido (intocable sin autorización explícita)
  scraper/scraper.py       — scrape_google_maps(keyword, city, limit, mode, cancel_event)
  scraper/classifier.py    — LeadClassifier, classifier singleton, filter_and_group()
  scraper/proxy.py         — Proxy HTTP con puertos dinámicos
  app.py                   — Flask legacy (endpoints /api/scrape, /api/download, etc.)
  google_sheets.py         — Integración Google Sheets

NIVEL B — V2 Arquitectura crítica (modificar con justificación, tests y revisión)
  modelos/lead.py          — Lead dataclass (cambio de contrato afecta todo V2)
  modelos/scrape_request.py  — ScrapeRequest dataclass
  modelos/source_config.py  — SourceConfig dataclass
  servicios/orquestador.py  — Pipeline completo V2
  servicios/fabrica_scrapers.py  — ScraperFactory (registry pattern)
  fuentes/base.py          — ScraperInterface (ABC compartido por todas las fuentes)

NIVEL C — Componentes evolutivos (libres de modificar con tests)
  servicios/normalizador.py
  servicios/validador.py
  servicios/deduplicator.py
  servicios/enriquecedor.py
  servicios/clasificador_servicio.py
  servicios/gestor_jobs.py
  fuentes/google_maps.py
  excepciones/*
  api/, persistencia/, exportadores/ (futuro)
  static/, templates/, docker/
  requirements.txt

REGLA DE AUTORIZACIÓN:
  Nivel A: requiere justificación documentada (README, docs/architecture/ o
    .kilo/plans/), mantener firmas/contratos, no romper legacy, aprobación explícita.
  Nivel B: requiere análisis de impacto, tests actualizados/nuevos, revisión de
    compatibilidad con fuentes existentes (Google Maps, DePeru).

## 3. Convenciones de código

  - **Idioma:** Escribir lógica nueva, variables, funciones, comentarios y
    docstrings en español. No traducir al español los contratos, interfaces,
    patrones o nombres técnicos ya establecidos en inglés (Lead, SourceConfig,
    ScraperInterface, GoogleMapsSource, SourceError, etc.). Priorizar
    consistencia arquitectónica sobre traducción literal.
  - **Logs:** siempre en español. Errores técnicos con doble resumen (inglés + español):
    ```python
    logger.error("Technical summary: timeout connecting to Google Maps | \
Resumen: no se pudo conectar con Google Maps. Reintenta en unos minutos.")
    ```
  - **Nombres de archivos:** snake_case descriptivo (normalizador.py, validador.py).
  - **Sin duplicar código:** revisar antes si existe lógica equivalente en legacy o V2
    (ver sección 5). Reutilizar imports read-only; no copiar.
  - **snake_case** para funciones/variables en español; nombres técnicos en inglés
    (Lead, ScraperInterface) conservan su nombre original.

## 4. Regla async

  Usar async para: scraping, I/O de red, concurrencia, tareas que realmente
  beneficien de async/await.

  Mantener síncronas: operaciones puramente CPU/memoria (normalización de
  campos, validación, deduplicación en memoria, cálculo de scores).

  No convertir a async sin justificación técnica. Si una función es pura
  CPU/memoria, no merece async.

  Ejemplo:
    async def scrape(request, cancel_event)  → I/O: scraping
    def normalizar_telefono(raw)            → CPU: regex, no async

## 5. No duplicar código — Patrones de reutilización

  ANTES de crear nueva lógica, revisar si existe reutilizable en legacy o V2.
  Patrones permitidos:

  1. ADAPTER — Envolver legacy con una interfaz V2.
     Ejemplo: fuentes/google_maps.py wrappea scraper.scraper.scrape_google_maps()
     → produce Lead[] (modelo unificado). El core sigue siendo el único scraper.

  2. WRAPPER — Delegación read-only de funcionalidad del core.
     Ejemplo: servicios/clasificador_servicio.py importa scraper.classifier.classifier
     → llama filter_and_group() para leads pendientes. No reescribe el algoritmo ML.

  3. DELEGATE — Reutilizar una función específica del core.
     Ejemplo: servicios/normalizador.py importa _normalizar_maps_url de scraper.scraper
     → no reimplementa la normalización de URLs.

  4. IMPORTS READ-ONLY — from scraper.X import Y (solo lectura).
     Importar funciones del core está permitido; reescribirlas, no.

  Regla de oro: si se duplica lógica que ya existe en legacy o V2, el agente
  debe justificar por qué no se reutilizó. Revisar antes de crear.

## 6. Integración de componentes V2

  1. Nuevos servicios: ubicar en servicios/ con nombre snake_case descriptivo.
     NO crear carpetas sueltas en raíz ni carpetas por "agente".
  2. No modificar Nivel B (orquestador.py, fabrica_scrapers.py) sin análisis.
  3. Nuevas fuentes: implementar ScraperInterface, registrar en ScraperFactory.
  4. Tests: pytest en tests/ con pytest-asyncio para tests async.
     Validar: python -m pytest tests/ -v
  5. Documentar cambios arquitectónicos en README o docs/architecture/.

## 7. Agregar nuevas fuentes

  1. Crear fuentes/<nombre_fuente>.py implementando ScraperInterface (definido en
     fuentes/base.py, Nivel B — no modificar su interfaz sin revisión).
  2. Registrar en fuentes/__init__.py: ScraperFactory.register(MiFuente()).
  3. Asignar SourceConfig con priority según confiabilidad, calidad, completitud
     y actualización de los datos. Los valores concretos son decisión del
     implementador, no una regla arquitectónica.
  4. Leads sin categoria_pred (fuente sin ML propio) serán clasificados por
     ClasificadorServicio en el pipeline. Leads con categoria_pred ya set (como
     Google Maps) se preservan (Opción C: evitar doble clasificación ML).
  5. Si la fuente reutiliza legacy (ej: wrapper de scrape_google_maps),
     importar read-only solo.
  6. Tests: tests/fuentes/test_<nombre_fuente>.py

## 8. Agregar nuevas funcionalidades

  - Persistencia (persistencia/): repository pattern. Usar modelos/lead.py
    como contrato. Implementar persistencia/lead_repository.py.
  - API (api/): async Flask. El Orquestador expone orquestar() como async.
  - Exportadores (exportadores/): usar Lead.to_dict() para serialización.
    No tocar el core legacy.
  - Dependencias nuevas: añadir solo en requirements.txt.
  - Frontend (templates/, static/): preservar compatibilidad visual y
    funcional con el UI legacy existente. Nuevos componentes deben integrarse
    sin romper layouts actuales.
  - Documentar: README (uso, instalación), docs/architecture/ (detalles técnicos
    o cambios arquitectónicos).

## 9. Logging y trazabilidad

  - Interfaz y logs de estado: siempre en español.
  - Mensajes orientados al usuario: adaptar idioma.
  - Errores técnicos: doble resumen (inglés + español).
  - Logs de error: incluir información de trazabilidad suficiente.
    Cuando exista job_id, request_id, source, user_id u otro identificador
    relevante disponible en el contexto, debe incluirse. No inventar
    identificadores que el contexto no proporcione.

    Ejemplo:
      logger.error(
        "job_id=%s source=%s error=%s | Technical summary: timeout | \
Resumen: no se pudo conectar. Reintentalo.",
        job_id, source, exc,
      )
  - Documentación (comentarios, docstrings): en español.

## 10. Regla de cambios arquitectónicos

  Cualquier cambio que afecte CONTRATOS entre capas, MODELOS principales,
  INTERFACES, el PIPELINE de orquestación o la ORGANIZACIÓN de carpetas
  debe analizarse antes de implementarse.

  No realizar refactorizaciones arquitectónicas grandes durante una tarea
  pequeña sin aprobación explícita. Si una tarea parece requerir cambios de
  esta magnitud, se debe:
    1. Documentar el cambio propuesto (alcance, impacto, alternativas).
    2. Obtener aprobación antes de implementarlo.
    3. Implementar con tests completos.

  Documentación en: README (general), docs/architecture/ (detallado técnico),
  o .kilo/plans/ (planificación).

## 11. Validación antes de terminar

  - python -m pytest tests/ -v           → toda la suite en verde.
  - python -m pytest tests/ -k deep -v   → validación del modo profundo.
  - Verificar que archivos de Nivel A y B no aparecen en git diff
    (salvo que el cambio esté justificado y documentado).
  - Verificar que no hay doble clasificación ML (core ya clasifica;
    ClasificadorServicio solo clasifica leads pendientes).
