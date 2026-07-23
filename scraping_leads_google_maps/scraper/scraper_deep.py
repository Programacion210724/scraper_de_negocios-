import asyncio
import csv
import os
import random
import re
from datetime import datetime
from playwright.async_api import async_playwright
from tqdm import tqdm

async def scrape_google_maps_deep():
    """
    Scraping profundo de Google Maps con clics individuales en cada negocio.
    """
    # Configuración
    keyword = input("Ingrese la palabra clave (ej: Dentistas): ").strip()
    city = input("Ingrese la ciudad (ej: Lima): ").strip()
    limit = int(input("Ingrese cuántos resultados desea (ej: 10, 50, 100): ").strip())

    # Archivo CSV de salida
    output_file = f"leads_{keyword.replace(' ', '_')}_{city}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_file = open(output_file, 'w', newline='', encoding='utf-8')
    writer = csv.writer(csv_file)
    writer.writerow(['nombre', 'direccion', 'categoria', 'telefono', 'sitio_web', 'maps_url'])

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        search_query = f"{keyword} {city}"
        url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Scroll dinámico para cargar resultados
        prev_count = 0
        no_change_count = 0
        max_scroll_attempts = 50

        print(f"Cargando {limit} resultados...")

        while True:
            listings = await page.query_selector_all('div[role="article"]')
            listings_loaded = len(listings)

            if listings_loaded >= limit:
                print(f"Cargados {listings_loaded} resultados")
                break

            if no_change_count >= 5 or listings_loaded >= 200:
                print(f"Cargados {listings_loaded} resultados (máximo alcanzado)")
                break

            # Scroll hacia abajo
            await page.evaluate("""() => {
                const scrollable = document.querySelector('div[role="feed"]');
                if (scrollable) {
                    scrollable.scrollBy(0, 500);
                }
            }""")

            await page.wait_for_timeout(random.randint(500, 1500))

            # Verificar si se cargaron nuevos
            if len(listings) == prev_count:
                no_change_count += 1
            else:
                no_change_count = 0
            prev_count = len(listings)

        # Limitar a la cantidad solicitada
        listings = await page.query_selector_all('div[role="article"]')
        listings = listings[:min(limit, len(listings))]
        print(f"Procesando {len(listings)} negocios...")

        # Progress bar con tqdm
        with tqdm(total=len(listings), desc="Extrayendo datos", unit="negocio") as pbar:
            for i, listing in enumerate(listings):
                try:
                    # Click en el negocio
                    await listing.click()

                    # Espera aleatoria anti-bot (2-4 segundos)
                    wait_time = random.uniform(2, 4)
                    await page.wait_for_timeout(wait_time * 1000)

                    # Extraer datos del panel derecho
                    nombre = ""
                    direccion = ""
                    categoria = ""
                    telefono = ""
                    sitio_web = ""
                    maps_url = ""

                    # Nombre
                    try:
                        name_elem = await page.query_selector('h1[data-attrid="title"], div[class*="qBF1Pd"], h1')
                        if name_elem:
                            nombre = (await name_elem.inner_text()).strip()
                    except:
                        pass

                    # Dirección
                    try:
                        addr_elem = await page.query_selector('button[data-item-id*="address"], div[data-item-id*="address"], span[aria-label*="Address"], button[aria-label*="Dirección"]')
                        if addr_elem:
                            direccion = (await addr_elem.inner_text()).strip()
                    except:
                        pass

                    # Categoría
                    try:
                        cat_elem = await page.query_selector('button[aria-label*="Categoría"], button[aria-label*="Category"]')
                        if cat_elem:
                            categoria = (await cat_elem.inner_text()).strip()
                    except:
                        pass

                    # Teléfono
                    try:
                        phone_elem = await page.query_selector('button[data-item-id*="phone"], button[aria-label*="tel"], a[aria-label*="tel"]')
                        if phone_elem:
                            telefono = (await phone_elem.get_attribute("aria-label") or await phone_elem.inner_text()).strip()
                            # Limpiar aria-label
                            if "tel" in telefono.lower() or "phone" in telefono.lower():
                                match = re.search(r"[\d\s\-\(\)\+]{7,15}", telefono)
                                if match:
                                    telefono = match.group()
                    except:
                        pass

                    # Sitio Web
                    try:
                        web_elem = await page.query_selector('a[data-item-id*="authority"], a[aria-label*="Sitio web"], a[aria-label*="Website"]')
                        if web_elem:
                            sitio_web = (await web_elem.get_attribute("href") or await web_elem.inner_text()).strip()
                    except:
                        pass

                    # URL del negocio
                    try:
                        current_url = page.url
                        if "google.com/maps/place" in current_url:
                            maps_url = current_url
                    except:
                        pass

                    # Si no hay teléfono, guardar "Sin número"
                    if not telefono:
                        telefono = "Sin número"

                    # Guardado en tiempo real
                    writer.writerow([nombre, direccion, categoria, telefono, sitio_web, maps_url])
                    csv_file.flush()

                    pbar.update(1)
                    pbar.set_postfix({"Actual": nombre[:30] if nombre else "N/A"})

                except Exception as e:
                    print(f"Error en negocio {i+1}: {e}")
                    pbar.update(1)
                    continue

        await browser.close()
        csv_file.close()
        print(f"\nDatos guardados en: {output_file}")

if __name__ == "__main__":
    asyncio.run(scrape_google_maps_deep())
