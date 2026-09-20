import asyncio
import logging
import os
import re
import random
import threading
import uuid
from urllib.parse import unquote

from playwright.async_api import async_playwright

from .classifier import classifier as _classifier
from .proxy import get_proxy_pool, close_proxy_pool

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

logger = logging.getLogger(__name__)

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "10"))
ROTATE_EVERY = int(os.environ.get("ROTATE_EVERY", "10"))
PROXY_ENABLED = os.environ.get("PROXY_ENABLED", "0") == "1"
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
BACKOFF_BASE = float(os.environ.get("BACKOFF_BASE", "2.0"))
MAX_CONSECUTIVE_EMPTY_BATCHES = int(os.environ.get("MAX_EMPTY_BATCHES", "8"))
MAX_SCROLL_STALLS = int(os.environ.get("MAX_SCROLL_STALLS", "30"))
EXTRACT_STALL_LIMIT = int(os.environ.get("EXTRACT_STALL_LIMIT", "5"))

CAPTCHA_SELECTORS = [
    'iframe[src*="recaptcha"]',
    'iframe[src*="captcha"]',
    'form[action*="sorry"]',
    '#captcha-form',
    '[role="dialog"] form input[name="captcha"]',
]

CAPTCHA_TEXT_TOKENS = ["captcha", "recaptcha", "verify you are human", "no soy un robot", "soy un robot"]


def _new_session_id() -> str:
    return f"session-{uuid.uuid4().hex[:8]}"


def _check_cancel(cancel_event) -> bool:
    if cancel_event and cancel_event.is_set():
        logger.info("Scraping cancelado por el usuario")
        return True
    return False


def _normalizar_maps_url(url: str) -> str:
    """Normaliza la URL de Google Maps para deduplicar.

    Google suele añadir tokens que cambian aunque sea el mismo local
    (parámetros `data=`, `ftid`, coordenadas `@...`, `!/...`). Se extrae la
    porción canónica `/place/<slug>` y se reconstruye una URL estable, de modo
    que URLs distintas del mismo negocio produzcan la misma clave.
    """
    if not url:
        return ""
    limpia = (url or "").strip()
    match = re.search(r"/place/([^/?#]+)", limpia)
    if match:
        slug = unquote(match.group(1)).replace("+", " ").strip()
        return f"https://maps.google.com/maps/place/{slug}/"
    # Fallback: quitar query, fragmento, tokens `!/...`, coordenadas `@...`
    limpia = re.sub(r"\?(.*)$", "", limpia)
    limpia = re.sub(r"#.*$", "", limpia)
    limpia = re.sub(r"[!?][^\s]*$", "", limpia)
    limpia = re.sub(r"@\d.*$", "", limpia)
    return limpia.strip()


def _dedup_key(result: dict) -> str:
    """Clave de deduplicación robusta.

    Prioriza la URL normalizada de maps; si no hay URL, combina
    nombre + teléfono + dirección (el teléfono es estable incluso si
    el resto varía entre apariciones).
    """
    url = _normalizar_maps_url(result.get("maps_url") or "")
    if url:
        return f"url:{url}"
    nombre = (result.get("nombre") or "").strip()
    telefono = (result.get("telefono") or "").strip()
    direccion = (result.get("direccion") or "").strip()
    return f"name:{nombre}|phone:{telefono}|addr:{direccion}"


async def _is_captcha(page) -> bool:
    """Detecta captchas/verificaciones en el DOM de la página."""
    try:
        for selector in CAPTCHA_SELECTORS:
            if await page.query_selector(selector):
                logger.warning("Captcha detectado (selector: %s)", selector)
                return True
        body_text = await page.evaluate("() => (document.body ? document.body.innerText : '')")
        lower = (body_text or "").lower()
        for token in CAPTCHA_TEXT_TOKENS:
            if token in lower:
                logger.warning("Captcha detectado (texto: %s)", token)
                return True
    except Exception:
        pass
    return False


async def _goto_with_retry(page, url: str, timeout: int = 60000, cancel_event=None) -> bool:
    """Navega a la URL con reintentos y back-off exponencial."""
    for attempt in range(1, MAX_RETRIES + 1):
        if _check_cancel(cancel_event):
            return False
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            if await _is_captcha(page):
                raise RuntimeError("Captcha detectado")
            return True
        except Exception as e:
            delay = BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, 1)
            message = str(e)
            if "captcha" in message.lower() or "Target closed" in message or "Navigation failed" in message or "net::" in message:
                logger.warning("Navegación bloqueada (intento %d/%d): %s. Reintento en %.1fs", attempt, MAX_RETRIES, message, delay)
            else:
                logger.debug("Error al navegar (intento %d/%d): %s", attempt, MAX_RETRIES, message)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(delay)
    return False


async def _extract_listing(listing, page, mode: str, url: str):
    """Extrae un listing individual. Devuelve (nombre, maps_url, phone, address)."""
    name_elem = await listing.query_selector("div.qBF1Pd")
    name = (await name_elem.inner_text()).strip() if name_elem else "Sin nombre"

    url_elem = await listing.query_selector("a.hfpxzc")
    maps_url = await url_elem.get_attribute("href") if url_elem else ""

    phone = ""
    address = ""

    if mode == 'deep':
        # --- EXTRACCIÓN PROFUNDA MEJORADA ---
        await listing.click()
        # Esperar explícitamente a que el elemento de teléfono esté visible
        phone_locator = page.locator('button[data-item-id*="phone"], [aria-label*="tel"], [aria-label*="Phone"]')
        try:
            await phone_locator.first.wait_for(state="visible", timeout=15000)
        except Exception as e:
            logger.debug(f"Teléfono no encontrado para '{name}': {e}")

        # Hacer scroll en el panel lateral para cargar más contenido
        try:
            sidebar = await page.query_selector('div[role="main"]')
            if sidebar:
                await sidebar.evaluate('el => el.scrollTo(0, el.scrollHeight)')
                await asyncio.sleep(2)
                await sidebar.evaluate('el => el.scrollTo(0, 0)')
                await asyncio.sleep(1)
        except Exception:
            pass

        # Buscar el teléfono probando múltiples selectores y atributos
        phone_selectors = [
            'button[data-item-id*="phone"]',
            '[aria-label*="Teléfono"]',
            '[aria-label*="Phone"]',
            'button[aria-label*="tel"]',
            'div[data-item-id*="phone"]',
            'span[data-item-id*="phone"]',
            'a[data-item-id*="phone"]'
        ]

        try:
            for selector in phone_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for elem in elements:
                        aria = await elem.get_attribute("aria-label") or ""
                        text = (await elem.inner_text() or "").strip()

                        if aria and any(char.isdigit() for char in aria) and "Llamar" not in aria and "Call" not in aria:
                            phone = re.sub(r'^(Teléfono|Phone):\s*', '', aria).strip()
                            if phone:
                                break
                        if text and any(char.isdigit() for char in text) and "Llamar" not in text and "Call" not in text:
                            phone = re.sub(r'^\s*(Llamar|Call)\s*', '', text).strip()
                            if phone:
                                break
                    if phone:
                        break
                except Exception:
                    continue

            # Si aún no encontramos, buscar en todo el panel lateral
            if not phone:
                phone_pattern_elements = await page.query_selector_all('div, span, p')
                for elem in phone_pattern_elements:
                    text = (await elem.inner_text() or "").strip()
                    match = re.search(r'(\+\d{1,3}[\s.-]?\d{6,14}|\d{7,15})', text)
                    if match and "Llamar" not in text and "Call" not in text and len(match.group(1)) > 7:
                        phone = match.group(1)
                        break
        except Exception as e:
            logger.debug(f"Teléfono no encontrado para '{name}': {e}")

        # Buscar dirección en el panel lateral
        addr_elem = await page.query_selector('button[data-item-id*="address"]')
        if addr_elem:
            address = (await addr_elem.inner_text()).strip()

        # Volver a la lista de resultados para que la siguiente iteración parta de un DOM limpio
        try:
            await page.go_back()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_selector('div[role="feed"]', timeout=10000)
            await asyncio.sleep(0.5)
        except Exception:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_selector('div[role="feed"]', timeout=15000)
            except Exception as e:
                logger.debug(f"No se pudo volver a la lista de resultados: {e}")
    else:
        # --- EXTRACCIÓN SIMPLE ---
        phone_buttons = await listing.query_selector_all('button[data-item-id*="phone"], [aria-label*="tel"]')
        if phone_buttons:
            aria = await phone_buttons[0].get_attribute("aria-label")
            phone = aria.replace("Teléfono: ", "").strip() if aria else await phone_buttons[0].inner_text()

        full_text = await listing.inner_text()
        addr_match = re.search(r"([^\n]+(?:calle|av|avenida|jr|cl|st|rd)[^\n]+)", full_text, re.IGNORECASE)
        if addr_match:
            address = addr_match.group(0).strip()

    return name, maps_url, phone, address


async def _extract_batch(page, url: str, keyword: str, city: str, batch_limit: int, mode: str, cancel_event) -> list:
    """Extrae un lote de resultados con scroll, partiendo de un DOM limpio.

    Cada elemento se vuelve a adquirir por índice desde el feed: tras el go_back
    del modo deep los ElementHandle previos quedan inválidos, así que re-consultar
    la lista garantiza un estado limpio en cada iteración.
    """
    results = []

    # Scroll inicial para cargar tantos resultados como sea posible
    scrolled_count = 0
    while scrolled_count < MAX_SCROLL_STALLS:
        if _check_cancel(cancel_event):
            return results
        current = len(await page.query_selector_all('div[role="article"]'))
        if current >= batch_limit:
            break
        try:
            await page.evaluate('(selector) => document.querySelector(selector).scrollBy(0, 1000)', 'div[role="feed"]')
        except Exception:
            break
        await asyncio.sleep(2)
        new_count = len(await page.query_selector_all('div[role="article"]'))
        if new_count <= current:
            scrolled_count += 1
        else:
            scrolled_count = 0

    # Extracción por índice, re-adquiriendo el handle en cada iteración
    processed = 0
    stall = 0
    while processed < batch_limit:
        if _check_cancel(cancel_event):
            return results
        listings = await page.query_selector_all('div[role="article"]')
        if processed >= len(listings):
            if stall >= EXTRACT_STALL_LIMIT:
                break
            try:
                await page.evaluate('(selector) => document.querySelector(selector).scrollBy(0, 1000)', 'div[role="feed"]')
            except Exception:
                break
            await asyncio.sleep(2)
            stall += 1
            continue
        listing = listings[processed]
        try:
            name, maps_url, phone, address = await _extract_listing(listing, page, mode, url)
            results.append({
                "nombre": name,
                "direccion": address,
                "telefono": phone,
                "ciudad": city,
                "categoria": keyword,
                "maps_url": maps_url
            })
            processed += 1
            stall = 0
        except Exception as e:
            print(f"Error en item: {e}")
            break

    return results


async def scrape_google_maps(keyword: str, city: str, limit: int = 20, mode: str = 'simple', cancel_event: threading.Event = None):
    results = []
    vistos = set()
    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
    os.makedirs(debug_dir, exist_ok=True)

    search_query = f"{keyword} {city}"
    url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"

    pool = None
    if PROXY_ENABLED:
        try:
            pool = await get_proxy_pool()
        except Exception as e:
            logger.warning("Proxy no disponible, continuando sin él: %s", e)
            pool = None

    batch_no = 0
    total_processed = 0
    empty_batches = 0

    try:
        async with async_playwright() as p:
            while len(results) < limit:
                if _check_cancel(cancel_event):
                    break

                if empty_batches >= MAX_CONSECUTIVE_EMPTY_BATCHES:
                    logger.warning("Demasiados lotes vacíos consecutivos, se detiene el scraping")
                    break

                batch_no += 1
                session_id = _new_session_id()
                remaining = limit - len(results)
                batch_limit = min(BATCH_SIZE, remaining)
                logger.info("[%s] Batch %d iniciado (objetivo: %d registros)", session_id, batch_no, batch_limit)

                # Estado limpio: nuevo navegador y contexto por lote
                browser = await p.chromium.launch(headless=True)
                try:
                    proxy_cfg = pool.next_proxy() if pool else None
                    context = await browser.new_context(user_agent=random.choice(USER_AGENTS), proxy=proxy_cfg)
                    page = await context.new_page()

                    ok = await _goto_with_retry(page, url, cancel_event=cancel_event)
                    if not ok:
                        if _check_cancel(cancel_event):
                            break
                        logger.warning("[%s] No se pudo cargar la página tras reintentos", session_id)
                        continue

                    await page.wait_for_selector('div[role="feed"]', timeout=15000)

                    batch_results = await _extract_batch(page, url, keyword, city, batch_limit, mode, cancel_event)

                    nuevos = []
                    for item in batch_results:
                        key = _dedup_key(item)
                        if key not in vistos:
                            vistos.add(key)
                            nuevos.append(item)
                    if nuevos:
                        logger.info("[%s] Batch %d: %d únicos (descartados %d duplicados)", session_id, batch_no, len(nuevos), len(batch_results) - len(nuevos))

                    results.extend(nuevos)
                    total_processed += len(nuevos)

                    if nuevos:
                        empty_batches = 0
                    else:
                        empty_batches += 1
                except Exception as e:
                    logger.warning("[%s] Error en batch: %s", session_id, e)
                    empty_batches += 1
                finally:
                    await browser.close()

                # Cerrar conexiones del proxy tras cada batch para evitar sobrecarga
                if pool:
                    pool.close_connections()

                # Rotación de IP/User-Agent cada N extracciones
                if total_processed > 0 and total_processed % ROTATE_EVERY == 0 and len(results) < limit:
                    logger.info("Rotación forzada de IP/User-Agent (%d extracciones procesadas)", total_processed)
    finally:
        if pool:
            await close_proxy_pool()

    # Filtrado y agrupación con ML antes de retornar
    if results:
        try:
            results = _classifier.filter_and_group(results, keyword)
            logger.info("Filtrado ML aplicado: %d leads válidos", len(results))
        except Exception as e:
            logger.warning("Filtrado ML no aplicado: %s", e)

    return results