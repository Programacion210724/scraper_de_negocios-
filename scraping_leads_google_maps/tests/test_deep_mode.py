"""
Tests del modo 'deep' del scraper con Playwright mockeado.

Verifican que el flujo profundo devuelve exactamente `limit` registros y que
cada registro contiene la clave `telefono` (nunca None ni ausente), sin depender
de red real.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from scraper.scraper import scrape_google_maps


class FakeElem:
    """Elemento DOM simulado con inner_text/get_attribute."""

    def __init__(self, text="", aria=None):
        self._text = text
        self._aria = aria

    async def inner_text(self):
        return self._text

    async def get_attribute(self, name):
        if name == "aria-label":
            return self._aria
        return None

    async def evaluate(self, *args, **kwargs):
        return None


class FakeSidebar(FakeElem):
    async def evaluate(self, *args, **kwargs):
        return None


def make_fake_listing(index):
    """Devuelve un listing con teléfono y dirección en el sidebar."""

    class FakeListing:
        async def query_selector(self, selector):
            if selector == "div.qBF1Pd":
                return FakeElem(text=f"Negocio {index}")
            if selector == "a.hfpxzc":
                return FakeElem(text="")
            return None

        async def query_selector_all(self, selector):
            return []

        async def inner_text(self):
            return f"Negocio {index}\nCalle Mayor {index}"

        async def click(self):
            return None

    return FakeListing()


class FakePage:
    def __init__(self, n_listings):
        self.n_listings = n_listings
        self._gone_back = False
        self.goto_calls = 0
        self._start = 0

    def locator(self, selector):
        first = MagicMock()
        first.wait_for = AsyncMock()
        return MagicMock(first=first)

    async def query_selector(self, selector):
        if selector == 'div[role="main"]':
            return FakeSidebar(text="")
        if selector == 'button[data-item-id*="address"]':
            return FakeElem(text=f"Calle Mayor 10, Madrid")
        if selector == "div.qBF1Pd":
            return None
        return None

    async def query_selector_all(self, selector):
        if selector == 'div[role="article"]':
            start = self._start
            end = start + self.n_listings
            return [make_fake_listing(i) for i in range(start + 1, end + 1)]
        if selector in (
            'button[data-item-id*="phone"]',
            '[aria-label*="Teléfono"]',
            '[aria-label*="Phone"]',
            'button[aria-label*="tel"]',
            'div[data-item-id*="phone"]',
            'span[data-item-id*="phone"]',
            'a[data-item-id*="phone"]',
        ):
            return [FakeElem(text=f"+34 912 345 6{str(self.n_listings).zfill(1)}", aria="Teléfono: +34 912 345 678")]
        if selector == "div, span, p":
            return []
        return []

    async def evaluate(self, *args, **kwargs):
        return ""

    async def goto(self, *args, **kwargs):
        self.goto_calls += 1
        return None

    async def wait_for_selector(self, *args, **kwargs):
        return None

    async def go_back(self):
        self._gone_back = True
        return None

    async def wait_for_load_state(self, *args, **kwargs):
        return None


class FakeContext:
    def __init__(self, page):
        self.page = page

    async def new_page(self):
        return self.page


class FakeBrowser:
    def __init__(self, page):
        self.page = page

    async def new_context(self, **kwargs):
        return FakeContext(self.page)

    async def close(self):
        return None


class FakeChromium:
    def __init__(self, page):
        self.page = page

    async def launch(self, **kwargs):
        self.page._start += 2
        return FakeBrowser(self.page)


class FakePlaywright:
    def __init__(self, page):
        self.chromium = FakeChromium(page)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_deep_mode_returns_limit_results_with_phone(monkeypatch):
    limit = 3
    page = FakePage(n_listings=limit)

    def fake_async_playwright():
        return FakePlaywright(page)

    monkeypatch.setattr("scraper.scraper.async_playwright", fake_async_playwright)

    results = await scrape_google_maps(
        keyword="restaurant", city="Madrid", limit=limit, mode="deep"
    )

    assert len(results) == limit, f"Se esperaban {limit} resultados, se obtuvieron {len(results)}"
    for r in results:
        assert "telefono" in r, "Cada registro debe contener la clave 'telefono'"
        assert r["telefono"] is not None, "El teléfono nunca debe ser None"


@pytest.mark.asyncio
async def test_deep_mode_generates_session_ids_and_reuses_list(monkeypatch):
    """Verifica que cada lote usa estado limpio (go_back) y genera sesiones nuevas."""
    limit = 3
    page = FakePage(n_listings=limit)

    def fake_async_playwright():
        return FakePlaywright(page)

    monkeypatch.setattr("scraper.scraper.async_playwright", fake_async_playwright)

    results = await scrape_google_maps(
        keyword="restaurant", city="Madrid", limit=limit, mode="deep"
    )

    assert page._gone_back is True, "El flujo deep debe volver a la lista (go_back)"
    assert all(isinstance(r["nombre"], str) for r in results)


@pytest.mark.asyncio
async def test_deep_mode_returns_no_none_phone_for_missing(monkeypatch):
    """Si no hay teléfono, el campo debe quedar en '' y el proceso continuar."""
    limit = 2

    class NoPhoneListing:
        def __init__(self, index):
            self.index = index

        async def query_selector(self, selector):
            if selector == "div.qBF1Pd":
                return FakeElem(text=f"Sin teléfono {self.index}")
            if selector == "a.hfpxzc":
                return FakeElem(text="")
            return None

        async def query_selector_all(self, selector):
            return []

        async def inner_text(self):
            return f"Sin teléfono {self.index}"

        async def click(self):
            return None

    class NoPhonePage(FakePage):
        async def query_selector_all(self, selector):
            if selector == 'div[role="article"]':
                return [NoPhoneListing(i) for i in range(1, limit + 1)]
            if selector in (
                'button[data-item-id*="phone"]',
                '[aria-label*="Teléfono"]',
                '[aria-label*="Phone"]',
                'button[aria-label*="tel"]',
                'div[data-item-id*="phone"]',
                'span[data-item-id*="phone"]',
                'a[data-item-id*="phone"]',
            ):
                return []
            if selector == "div, span, p":
                return []
            return []

        async def query_selector(self, selector):
            if selector == 'div[role="main"]':
                return FakeSidebar(text="")
            if selector == 'button[data-item-id*="address"]':
                return FakeElem(text="Calle Mayor 10, Madrid")
            return None

    nophone_page = NoPhonePage(n_listings=limit)

    def fake_async_playwright():
        return FakePlaywright(nophone_page)

    monkeypatch.setattr("scraper.scraper.async_playwright", fake_async_playwright)

    results = await scrape_google_maps(
        keyword="restaurant", city="Madrid", limit=limit, mode="deep"
    )

    assert len(results) == limit
    for r in results:
        assert "telefono" in r
        assert r["telefono"] == "", "Sin teléfono disponible debe quedar como cadena vacía, no None"


@pytest.mark.asyncio
async def test_deep_mode_multi_batch_reaches_limit(monkeypatch):
    """Con BATCH_SIZE pequeño, el bucle debe rotar sesiones hasta completar el límite."""
    limit = 5
    page = FakePage(n_listings=limit)

    def fake_async_playwright():
        return FakePlaywright(page)

    monkeypatch.setattr("scraper.scraper.async_playwright", fake_async_playwright)
    monkeypatch.setattr("scraper.scraper.BATCH_SIZE", 2)
    monkeypatch.setattr("scraper.scraper.ROTATE_EVERY", 10)

    results = await scrape_google_maps(
        keyword="restaurant", city="Madrid", limit=limit, mode="deep"
    )

    assert len(results) == limit, f"Se esperaban {limit} resultados, se obtuvieron {len(results)}"
    for r in results:
        assert "telefono" in r
        assert r["telefono"] is not None