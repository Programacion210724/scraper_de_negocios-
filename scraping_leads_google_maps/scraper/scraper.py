import asyncio
import os
import re
import random
import threading
from playwright.async_api import async_playwright

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

async def scrape_google_maps(keyword: str, city: str, limit: int = 20, mode: str = 'simple', cancel_event: threading.Event = None):
    results = []
    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
    os.makedirs(debug_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
        page = await context.new_page()

        search_query = f"{keyword} {city}"
        url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_selector('div[role="feed"]', timeout=15000)
        except Exception as e:
            print(f"Error inicial: {e}")
            await browser.close()
            return []

        # Scroll para cargar resultados
        scrolled_count = 0
        while len(await page.query_selector_all('div[role="article"]')) < limit and scrolled_count < 20:
            if cancel_event and cancel_event.is_set():
                print("Scraping cancelado por el usuario")
                await browser.close()
                return results
            await page.evaluate('(selector) => document.querySelector(selector).scrollBy(0, 1000)', 'div[role="feed"]')
            await asyncio.sleep(2)
            if len(await page.query_selector_all('div[role="article"]')) <= len(results):
                scrolled_count += 1
            else:
                scrolled_count = 0

        listings = await page.query_selector_all('div[role="article"]')
        
        for listing in listings[:limit]:
            if cancel_event and cancel_event.is_set():
                print("Scraping cancelado por el usuario")
                break
                
            try:
                name_elem = await listing.query_selector("div.qBF1Pd")
                name = (await name_elem.inner_text()).strip() if name_elem else "Sin nombre"
                
                url_elem = await listing.query_selector("a.hfpxzc")
                maps_url = await url_elem.get_attribute("href") if url_elem else ""

                phone = ""
                address = ""

                if mode == 'deep':
                    # --- EXTRACCIÓN PROFUNDA MEJORADA ---
                    await listing.click()
                    await asyncio.sleep(3) # Esperar un poco más para asegurar la carga del panel
                    
                    # Hacer scroll en el panel lateral para cargar más contenido
                    try:
                        sidebar = await page.query_selector('div[role="main"]')
                        if sidebar:
                            await sidebar.evaluate('el => el.scrollTo(0, el.scrollHeight)')
                            await asyncio.sleep(2)
                            await sidebar.evaluate('el => el.scrollTo(0, 0)')
                            await asyncio.sleep(1)
                    except:
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
                        except:
                            continue
                    
                    # Si aún no encontramos, buscar en todo el panel lateral
                    if not phone:
                        try:
                            phone_pattern_elements = await page.query_selector_all('div, span, p')
                            for elem in phone_pattern_elements:
                                text = (await elem.inner_text() or "").strip()
                                match = re.search(r'(\+\d{1,3}[\s.-]?\d{6,14}|\d{7,15})', text)
                                if match and "Llamar" not in text and "Call" not in text and len(match.group(1)) > 7:
                                    phone = match.group(1)
                                    break
                        except:
                            pass
                    
                    # Buscar dirección en el panel lateral
                    addr_elem = await page.query_selector('button[data-item-id*="address"]')
                    if addr_elem:
                        address = (await addr_elem.inner_text()).strip()
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

                results.append({
                    "nombre": name,
                    "direccion": address,
                    "telefono": phone,
                    "ciudad": city,
                    "categoria": keyword,
                    "maps_url": maps_url
                })
            except Exception as e:
                print(f"Error en item: {e}")
                continue

        await browser.close()
    return results