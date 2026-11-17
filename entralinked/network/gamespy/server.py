"""The GameSpy presence server (gpcm.gs.nintendowifi.net)."""
import logging
import socketserver
import threading

from ...context import Context
from .handler import GameSpyHandler

logger = logging.getLogger(__name__)

GAMESPY_PORT = 29900  # fixed by the protocol


class _ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    context: Context


class GameSpyServer:
    """Listens for consoles and gives each connection its own GameSpyHandler thread."""

    def __init__(self, context: Context, port: int = GAMESPY_PORT) -> None:
        self.context = context
        self.port = port
        self.server: _ThreadedTCPServer | None = None
        self.server_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start listening."""
        self.server = _ThreadedTCPServer(("0.0.0.0", self.port), GameSpyHandler)
        self.server.context = self.context

        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        logger.info("GameSpy server listening @ port %d", self.port)

    def stop(self) -> None:
        """Stop listening. Do nothing if the server isn't running."""
        if self.server is None:
            return

        self.server.shutdown()
        self.server.server_close()
        if self.server_thread is not None:
            self.server_thread.join()

        self.server = None
        self.server_thread = None
        logger.info("GameSpy server stopped")
