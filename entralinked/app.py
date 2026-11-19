"""Starts the DNS, HTTP(S), and GameSpy servers that make up the Game Sync server."""
import argparse
import dataclasses
import logging
import signal
import socket
import sys
import threading
import time

from .configuration import LOCAL_HOST_NAMES, Configuration, load_configuration
from .context import Context
from .model.dlc.dlc import DlcList
from .model.player.player_manager import PlayerManager
from .model.user.user_manager import UserManager
from .network.dns.server import DnsServer
from .network.gamespy.server import GameSpyServer
from .network.http.http_server import HTTP_PORT, HttpServer
from .paths import CONFIG_PATH
from .utility.db_manager import db

logger = logging.getLogger(__name__)


def get_local_address() -> str:
    """Return this machine's address on the local network."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def resolve_host_address(configuration: Configuration) -> str:
    """Return the address the DNS server gives out for every name."""
    if configuration.host_name in LOCAL_HOST_NAMES:
        return get_local_address()
    return socket.gethostbyname(configuration.host_name)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line options."""
    parser = argparse.ArgumentParser(description="Game Sync server")
    parser.add_argument("--host", help='the host name the DNS server gives out, such as your public '
                                       'address so others can connect. Overrides "host_name" in config.json, '
                                       'and "local" means this machine\'s address on the local network')
    parser.add_argument("--http-port", type=int, default=HTTP_PORT,
                        help=f"the port for plain HTTP (default {HTTP_PORT}, which the DS uses). Change it only "
                             "when a web server on this machine passes port 80 on to this one")
    return parser


def main() -> int:
    """Run the servers until SIGINT or SIGTERM and return the exit code.

    The exit code is 1 if a server couldn't start (usually a port that is taken,
    or that needs root).
    """
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    started_at = time.perf_counter()

    configuration = load_configuration(CONFIG_PATH)
    if args.host:
        configuration = dataclasses.replace(configuration, host_name=args.host)
    logger.info("Using configuration %s", configuration)

    context = Context(configuration, UserManager(), PlayerManager(), DlcList())
    host_address = resolve_host_address(configuration)
    servers = (DnsServer(host_address), HttpServer(context, args.http_port), GameSpyServer(context))

    stop_requested = threading.Event()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signal_number, lambda *_: stop_requested.set())

    exit_code = 0
    try:
        for server in servers:
            server.start()

        logger.info("Startup complete! Took %d milliseconds", (time.perf_counter() - started_at) * 1000)
        logger.info("Configure your DS to use the following DNS server: %s", host_address)

        while not stop_requested.wait(1.0):  # in short waits, so that Windows gets to deliver Ctrl+C
            pass
    except Exception:
        logger.exception("Failed to start servers")
        exit_code = 1
    finally:
        logger.info("Stopping servers ...")
        for server in reversed(servers):
            try:
                server.stop()
            except Exception:
                logger.exception("Could not stop %s", type(server).__name__)
        db.close()

    return exit_code
