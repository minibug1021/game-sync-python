"""Messages sent by the GameSpy server."""
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class GameSpyMessage:
    r"""Base class for messages, which start with `\<NAME>\<VALUE>`."""

    NAME: ClassVar[str]
    VALUE: ClassVar[str] = ""


@dataclass
class GameSpyChallengeMessage(GameSpyMessage):
    """Sent as soon as a console connects."""

    NAME = "lc"
    VALUE = "1"

    challenge: str
    id: int


@dataclass
class GameSpyErrorMessage(GameSpyMessage):
    """Error. `fatal` is 1 if the console should give up."""

    NAME = "error"

    err: int
    errmsg: str
    fatal: int
    id: int


@dataclass
class GameSpyLoginResponse(GameSpyMessage):
    """The reply to a successful login."""

    NAME = "lc"
    VALUE = "2"

    userid: str
    profileid: int
    proof: str
    sesskey: int
    id: int


@dataclass
class GameSpyProfileResponse(GameSpyMessage):
    """A profile's details."""

    NAME = "pi"

    profileid: int
    firstname: str | None
    lastname: str | None
    aim: str | None
    zipcode: str | None
    sig: str
    id: int
