"""Sessions that let a logged-in console use one of the other services."""
from dataclasses import dataclass
from datetime import datetime

from .user import User


@dataclass
class ServiceSession:
    """The server's side of a token handed to the console."""

    user: User
    service: str
    branch_code: str | None  # which game's profile to use (GameSpy only)
    challenge_hash: str
    expiry: datetime

    def has_expired(self) -> bool:
        """Whether the token can no longer be used."""
        return datetime.now() > self.expiry
