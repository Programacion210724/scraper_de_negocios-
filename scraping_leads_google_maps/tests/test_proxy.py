"""Tests del servicio de proxy: puertos dinámicos y rotación por lote."""

import asyncio

import pytest

from scraper.proxy import ForwardProxyServer, ProxyPool


@pytest.mark.asyncio
async def test_proxy_server_binds_dynamic_port():
    server = ForwardProxyServer()
    await server.start()
    assert server.port > 0, "El listener debe usar un puerto dinámico (port 0)"
    await server.stop()


@pytest.mark.asyncio
async def test_proxy_pool_rotates_ports_every_ten():
    pool = ProxyPool(ports=3)
    await pool.start()
    assert len(pool.servers) == 3
    assert all(s.port > 0 for s in pool.servers)

    seen = set()
    for i in range(10):
        cfg = pool.next_proxy()
        assert cfg is not None
        assert cfg["server"].startswith("http://127.0.0.1:")
        seen.add(cfg["server"])

    # Con 3 puertos y 10 extracciones debe haber rotado (>=2 puertos usados)
    assert len(seen) >= 2, "Debe rotar entre puertos dentro de 10 extracciones"

    await pool.stop()


@pytest.mark.asyncio
async def test_proxy_pool_close_connections_after_batch():
    pool = ProxyPool(ports=2)
    await pool.start()
    for _ in range(4):
        pool.next_proxy()
    # Cerrar conexiones tras el batch no debe romper la rotación posterior
    pool.close_connections()
    cfg = pool.next_proxy()
    assert cfg is not None
    await pool.stop()


@pytest.mark.asyncio
async def test_proxy_pool_next_proxy_none_when_empty():
    pool = ProxyPool(ports=0)
    await pool.start()
    assert len(pool.servers) >= 1
    cfg = pool.next_proxy()
    assert cfg is not None
    await pool.stop()