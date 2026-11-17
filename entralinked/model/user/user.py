"""A Nintendo WFC account."""
from dataclasses import dataclass, field

from .game_profile import GameProfile


@dataclass
class User:
    """A console's Nintendo WFC account."""

    id: str
    password: str
    profiles: dict[str, GameProfile] = field(default_factory=dict)

    @property
    def redacted_id(self) -> str:
        return f"{self.id[:4]}-XXXX-XXXX-XXXX"
