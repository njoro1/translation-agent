"""Unit tests for src.local_server server-handling helpers.

These cover the port-discovery and model-validation logic that prevents the
app from blind-reusing a stale/foreign server on the configured port (which
previously caused HTTP 405 hangs against a non-llama server).
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.local_server import (
    _find_free_port,
    _port_free,
    server_serves_model,
)


def _start_server(handler_cls) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class _ModelListHandler(BaseHTTPRequestHandler):
    """Serves /v1/models advertising a fixed model id."""

    def do_GET(self):  # noqa: N802
        if self.path == "/v1/models":
            body = json.dumps({"data": [{"id": "Hy-MT2-1.8B-Q8_0"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # noqa: D401
        pass


class _MethodNotAllowedHandler(BaseHTTPRequestHandler):
    """Returns 405 on /v1/models — a server that is NOT llama-server."""

    def do_GET(self):  # noqa: N802
        self.send_response(405)
        self.end_headers()

    def log_message(self, *args):  # noqa: D401
        pass


def test_port_free_finds_free_high_port() -> None:
    # A port that is almost certainly never bound.
    assert _port_free("127.0.0.1", 65500) is True


def test_find_free_port_returns_open_port() -> None:
    port = _find_free_port("127.0.0.1", 10000)
    assert _port_free("127.0.0.1", port) is True


def test_server_serves_model_matches_expected_gguf() -> None:
    server = _start_server(_ModelListHandler)
    try:
        host, port = "127.0.0.1", server.server_address[1]
        assert server_serves_model(host, port, "C:/models/Hy-MT2-1.8B-Q8_0.gguf") is True
        # Different model => not reusable for this request.
        assert (
            server_serves_model(host, port, "C:/models/other-model.gguf") is False
        )
    finally:
        server.shutdown()
        server.server_close()


def test_server_serves_model_rejects_non_llama_server() -> None:
    # A server answering 405 on /v1/models must NOT be treated as reusable.
    server = _start_server(_MethodNotAllowedHandler)
    try:
        host, port = "127.0.0.1", server.server_address[1]
        assert server_serves_model(host, port, "Hy-MT2-1.8B-Q8_0.gguf") is False
    finally:
        server.shutdown()
        server.server_close()


def test_server_serves_model_returns_false_when_nothing_listening() -> None:
    assert server_serves_model("127.0.0.1", 65500, "Hy-MT2-1.8B-Q8_0.gguf") is False