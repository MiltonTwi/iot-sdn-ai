#!/usr/bin/env python3
"""Servidor HTTP del lab (sustituye a `python3 -m http.server`).

`http.server` (ThreadingHTTPServer) crea un hilo por conexión sin límite ni
timeout. Bajo HTTP flood llegó a ~4100 hilos, chocó con pids.max del
container y quedó atascado (hilos en futex, CPU ~3 %) → los ataques
siguientes fallaban con "can't start new thread".

Aquí: pool FIJO de workers + timeout de socket. Las conexiones que exceden el
pool esperan en cola (backlog) → el DoS se manifiesta como latencia/rechazo,
igual que en un Apache/nginx con MaxRequestWorkers, sin tumbar el container.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from http.server import HTTPServer, SimpleHTTPRequestHandler

READ_TIMEOUT_S = 30
MAX_WORKERS = 256


class Handler(SimpleHTTPRequestHandler):
    timeout = READ_TIMEOUT_S  # StreamRequestHandler → socket.settimeout

    def log_message(self, *_):  # silencio: miles de req/s en floods
        pass


class PooledHTTPServer(HTTPServer):
    request_queue_size = 1024
    _pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    def process_request(self, request, client_address):
        self._pool.submit(self._work, request, client_address)

    def _work(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            pass
        finally:
            self.shutdown_request(request)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    srv = PooledHTTPServer(("0.0.0.0", port), lambda *a: Handler(*a, directory="/tmp"))
    srv.serve_forever()


if __name__ == "__main__":
    main()
