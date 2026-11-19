"""The web server for everything the DS reaches over HTTP."""
import io
import logging
import socketserver
import threading
from collections.abc import Callable, Iterable
from typing import Any
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer

from flask import Flask
from tlslite import TLSSocketServerMixIn, X509CertChain
from tlslite.handshakesettings import HandshakeSettings
from tlslite.sessioncache import SessionCache
from tlslite.utils.keyfactory import parsePEMKey
from werkzeug.serving import BaseWSGIServer, make_server

from ...context import Context
from ...paths import SERVER_PEM_PATH
from .dls_handler import DlsHandler
from .nas_handler import NasHandler
from .pgl_handler import PglHandler

logger = logging.getLogger(__name__)

HTTPS_PORT = 443  # the DS is only given an address, so the port can't change
HTTP_PORT = 80  # the DS asks for port 80


class RequestBodyMiddleware:
    def __init__(self, wsgi_app: Callable[..., Iterable[bytes]]) -> None:
        self.wsgi_app = wsgi_app

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        try:
            remaining = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            remaining = 0

        wsgi_input = environ.get("wsgi.input")

        if remaining > 0 and wsgi_input is not None:
            chunks = []

            while remaining > 0:
                chunk = wsgi_input.read(remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)

            body = b"".join(chunks)
            environ["wsgi.input"] = io.BytesIO(body)
            environ["CONTENT_LENGTH"] = str(len(body))

        return self.wsgi_app(environ, start_response)


class TLSServer(TLSSocketServerMixIn, socketserver.ThreadingMixIn, WSGIServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, private_key: Any, cert_chain: X509CertChain, app: Flask) -> None:
        super().__init__(("0.0.0.0", HTTPS_PORT), WSGIRequestHandler)
        self.private_key = private_key
        self.cert_chain = cert_chain
        self.session_cache = SessionCache()
        self.set_app(app)

    def handshake(self, connection: Any) -> bool:
        settings = HandshakeSettings()
        settings.minVersion = (3, 0)
        settings.maxVersion = (3, 1)
        settings.cipherNames = ["rc4"]
        settings.macNames = ["md5", "sha"]
        settings.keyExchangeNames = ["rsa"]

        connection.handshakeServer(
            privateKey=self.private_key,
            certChain=self.cert_chain,
            settings=settings,
            sessionCache=self.session_cache,
        )
        return True


def create_app(context: Context) -> Flask:
    """Create the Flask app with the handler's routes."""
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    app.wsgi_app = RequestBodyMiddleware(app.wsgi_app)

    for handler in (NasHandler(context), PglHandler(context), DlsHandler(context)):
        app.register_blueprint(handler.blueprint())

    @app.route("/")
    def conntest() -> tuple[str, int, dict[str, str]]:
        """Answer the DS's connection test, which fails without this header."""
        return "Test", 200, {"X-Organization": "Nintendo"}

    return app


class HttpServer:
    """Serves the app over HTTP(S)."""

    def __init__(self, context: Context, http_port: int = HTTP_PORT) -> None:
        self.app = create_app(context)
        self.http_port = http_port
        self.http_server: BaseWSGIServer | None = None
        self.http_thread: threading.Thread | None = None
        self.server: TLSServer | None = None
        self.server_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the HTTP and HTTPS servers."""
        self.http_server = make_server("0.0.0.0", self.http_port, self.app, threaded=True)
        self.http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
        self.http_thread.start()
        logger.info("HTTP server listening @ port %d", self.http_port)

        pem = SERVER_PEM_PATH.read_text(encoding="UTF-8") # update the cert in 2076
        chain = X509CertChain()
        chain.parsePemList(pem)
        self.server = TLSServer(parsePEMKey(pem, private=True), chain, self.app)

        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        logger.info("HTTPS server listening @ port %d", HTTPS_PORT)

    def stop(self) -> None:
        """Stop listening. Do nothing for a server that isn't running."""
        for name, server, thread in (("HTTP", self.http_server, self.http_thread),
                                     ("HTTPS", self.server, self.server_thread)):
            if server is None:
                continue
            server.shutdown()
            server.server_close()
            if thread is not None:
                thread.join()
            logger.info("%s server stopped", name)

        self.http_server = self.http_thread = self.server = self.server_thread = None
