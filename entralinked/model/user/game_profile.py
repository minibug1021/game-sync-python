"""A GameSpy profile."""
from dataclasses import dataclass


@dataclass
class GameProfile:
    id: int
    firstname: str | None = None
    lastname: str | None = None
    aim: str | None = None
    zipcode: str | None = None
