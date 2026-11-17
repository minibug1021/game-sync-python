"""A DNS server."""
import logging

from dnslib import QTYPE, RR, A
from dnslib.server import BaseResolver, DNSHandler, DNSRecord, DNSServer

logger = logging.getLogger(__name__)

DNS_PORT = 53  # the DS is only given an address, so the port can't change


class FixedResolver(BaseResolver):
    """Resolves every A query to one address."""

    def __init__(self, host_address: str) -> None:
        self.host_address = host_address

    def resolve(self, request: DNSRecord, handler: DNSHandler) -> DNSRecord:
        """Answer one query."""
        reply = request.reply()

        if request.q.qtype == QTYPE.A:
            reply.add_answer(RR(request.q.qname, QTYPE.A, rdata=A(self.host_address), ttl=0))
        else:
            logger.warning("Unsupported record type in DNS question: %s", request.q.qtype)

        return reply


class DnsServer:
    """Runs the resolver on UDP port 53."""

    def __init__(self, host_address: str) -> None:
        self.host_address = host_address
        self.server: DNSServer | None = None

    def start(self) -> None:
        """Start answering queries."""
        self.server = DNSServer(FixedResolver(self.host_address), port=DNS_PORT)
        self.server.start_thread()
        logger.info("DNS server listening @ port %d", DNS_PORT)

    def stop(self) -> None:
        """Stop the server. Do nothing if it isn't running."""
        if self.server is None:
            return

        self.server.stop()
        self.server = None
        logger.info("DNS server stopped")
