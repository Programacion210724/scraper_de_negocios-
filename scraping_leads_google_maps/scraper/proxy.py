"""
Servicio de proxy HTTP (forward proxy) para rotar peticiones de Playwright.

Implementa un proxy CONNECT (túnel para HTTPS, que es lo que usa Google Maps)
escuchando en puertos dinámicos. Cada listener puede salir por un upstream
distinto (rotación de IP) o directo. El pool rota el puerto de salida y las
conexiones se cierran tras cada batch para evitar sobrecarga.

Configuración vía variables de entorno:
  - PROXY_ENABLED=1                     Activa el proxy.
  - PROXY_PORTS=0                       Lista de puertos (0 = dinámico).
  - PROXY_UPSTREAMS=host:port[,host:port]  Upstreams de salida (opcional).
  - PROXY_ROTATE_EVERY=N                Rotar puerto/UA cada N extracciones.
"""

import asyncio
import logging
import random

logger = logging.getLogger(__name__)


class ForwardProxyConnection:
    """Maneja una conexión de cliente hacia el proxy."""

    def __init__(self, reader, writer, upstream=None, on_closed=None):
        self.reader = reader
        self.writer = writer
        self.upstream = upstream
        self.on_closed = on_closed
        self.buffer = b""
        self.connected = True
        self.tasks = []

    async def handle(self) -> None:
        try:
            first_line = await self._read_http_header()
            if not first_line:
                return
            method, target = self._parse_request(first_line)
            if method == "CONNECT":
                await self._handle_connect(target)
            else:
                await self._handle_plain_http(method, target)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Error en conexión proxy: %s", e)
            try:
                self.writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                await self.writer.drain()
            except Exception:
                pass
        finally:
            self.close()

    async def _read_http_header(self) -> str:
        """Lee el header HTTP (hasta \\r\\n\\r\\n)."""
        while b"\r\n\r\n" not in self.buffer:
            chunk = await self.reader.read(4096)
            if not chunk:
                return ""
            self.buffer += chunk
            if len(self.buffer) > 65536:
                return ""
        head, self.buffer = self.buffer.split(b"\r\n\r\n", 1)
        return head.decode("latin-1")

    @staticmethod
    def _parse_request(header: str):
        lines = header.split("\r\n")
        try:
            method, target, _ = lines[0].split(" ", 2)
        except ValueError:
            method, target = lines[0].split(" ", 1)
        return method.upper(), target.strip()

    async def _open_outbound(self, host: str, port: int):
        """Conecta al upstream si existe, si no directo."""
        if self.upstream:
            up_host, up_port = self.upstream
            logger.debug("Proxy saliendo por upstream %s:%s", up_host, up_port)
            return await asyncio.open_connection(up_host, up_port)
        return await asyncio.open_connection(host, port)

    async def _handle_connect(self, target: str) -> None:
        if ":" not in target:
            return
        host, port_str = target.rsplit(":", 1)
        port = int(port_str)

        out_reader, out_writer = await self._open_outbound(host, port)

        if self.upstream:
            # Reenviar CONNECT al upstream
            req = f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n"
            out_writer.write(req.encode("latin-1"))
            await out_writer.drain()
            resp_head = b""
            while b"\r\n\r\n" not in resp_head:
                chunk = await out_reader.read(4096)
                if not chunk:
                    break
                resp_head += chunk
            status_line = resp_head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
            self.writer.write((status_line + "\r\n\r\n").encode("latin-1"))
            await self.writer.drain()
        else:
            self.writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await self.writer.drain()

        # Túnel bidireccional
        await self._relay(out_reader, out_writer)

    async def _handle_plain_http(self, method: str, target: str) -> None:
        import urllib.parse
        parsed = urllib.parse.urlparse(target)
        host = parsed.hostname or "localhost"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        out_reader, out_writer = await self._open_outbound(host, port)
        head = self.buffer.decode("latin-1") if self.buffer else ""
        request = f"{method} {path} HTTP/1.1\r\nHost: {host}:{port}\r\n{head}"
        out_writer.write(request.encode("latin-1"))
        await out_writer.drain()
        await self._relay(out_reader, out_writer)

    async def _relay(self, out_reader, out_writer) -> None:
        async def pipe(src, dst):
            try:
                while True:
                    data = await src.read(65536)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            except Exception:
                pass
            finally:
                try:
                    dst.close()
                except Exception:
                    pass

        t1 = asyncio.ensure_future(pipe(self.reader, out_writer))
        t2 = asyncio.ensure_future(pipe(out_reader, self.writer))
        self.tasks = [t1, t2]
        await asyncio.gather(t1, t2, return_exceptions=True)

    def close(self) -> None:
        if not self.connected:
            return
        self.connected = False
        try:
            self.writer.close()
        except Exception:
            pass
        if self.on_closed:
            self.on_closed(self)


class ForwardProxyServer:
    """Listener individual del pool, con upstream de salida opcional."""

    def __init__(self, upstream=None):
        self.upstream = upstream
        self.server = None
        self.port = 0
        self.clients = []

    async def start(self) -> None:
        self.server = await asyncio.start_server(
            self._client_connected,
            host="127.0.0.1",
            port=0,
        )
        self.port = self.server.sockets[0].getsockname()[1]
        logger.info("Proxy escuchando en 127.0.0.1:%d (upstream=%s)", self.port, self.upstream or "directo")

    def _client_connected(self, reader, writer):
        conn = ForwardProxyConnection(reader, writer, self.upstream, on_closed=self._on_client_closed)
        self.clients.append(conn)
        asyncio.ensure_future(conn.handle())

    def _on_client_closed(self, conn):
        if conn in self.clients:
            self.clients.remove(conn)

    def close_connections(self) -> None:
        for conn in list(self.clients):
            conn.close()
        self.clients.clear()
        logger.info("Conexiones del proxy cerradas tras el batch (puerto %d)", self.port)

    async def stop(self) -> None:
        self.close_connections()
        if self.server:
            self.server.close()
            await self.server.wait_closed()


class ProxyPool:
    """Pool de listeners: rota puerto de salida y gestiona el ciclo de vida."""

    def __init__(self, ports: int = 0, upstreams=None):
        self.port_count = max(1, int(ports or 1))
        self.upstreams = upstreams or []
        self.servers = []
        self._cursor = 0

    async def start(self) -> None:
        for i in range(self.port_count):
            upstream = self.upstreams[i % len(self.upstreams)] if self.upstreams else None
            server = ForwardProxyServer(upstream=upstream)
            await server.start()
            self.servers.append(server)
        logger.info("ProxyPool activo con %d puertos", len(self.servers))

    def next_proxy(self):
        """Devuelve la configuración del siguiente proxy rotando el puerto."""
        if not self.servers:
            return None
        server = self.servers[self._cursor % len(self.servers)]
        self._cursor += 1
        cfg = {"server": f"http://127.0.0.1:{server.port}"}
        logger.debug("Rotando a proxy %s (extracción %d)", cfg["server"], self._cursor)
        return cfg

    def close_connections(self) -> None:
        for server in self.servers:
            server.close_connections()

    async def stop(self) -> None:
        for server in self.servers:
            await server.stop()
        self.servers.clear()


_pool = None


async def get_proxy_pool() -> ProxyPool:
    """Devuelve el pool compartido, arrancándolo la primera vez."""
    global _pool
    if _pool is None:
        import os
        enabled = os.environ.get("PROXY_ENABLED", "0") == "1"
        if not enabled:
            _pool = None
            return None
        ports = os.environ.get("PROXY_PORTS", "0")
        upstreams_raw = os.environ.get("PROXY_UPSTREAMS", "")
        upstreams = []
        for pair in upstreams_raw.split(","):
            pair = pair.strip()
            if ":" in pair:
                host, port = pair.rsplit(":", 1)
                upstreams.append((host, int(port)))
        _pool = ProxyPool(ports=ports, upstreams=upstreams)
        await _pool.start()
    return _pool


async def close_proxy_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.stop()
        _pool = None