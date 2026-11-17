"""Requests a console sends to the GameSpy server."""
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class GameSpyRequest:
    """Base class of the requests the GameSpy server handles.

    COMMAND is the first key of the message, and requests with NEEDS_SESSION are
    only handled once the connection has logged in.
    """

    COMMAND: ClassVar[str]
    NEEDS_SESSION: ClassVar[bool] = True


@dataclass
class GameSpyKeepAliveRequest(GameSpyRequest):
    """Heartbeat request to keep the connection alive."""

    COMMAND = "ka"
    NEEDS_SESSION = False


@dataclass
class GameSpyLoginRequest(GameSpyRequest):
    """Logs in with the token and challenge that NAS handed out."""

    COMMAND = "login"
    NEEDS_SESSION = False

    response: str
    challenge: str
    authtoken: str
    id: int


@dataclass
class GameSpyLogoutRequest(GameSpyRequest):
    """Ends the session."""

    COMMAND = "logout"

    sesskey: int


@dataclass
class GameSpyProfileRequest(GameSpyRequest):
    """Asks for the logged-in profile's details."""

    COMMAND = "getprofile"

    sesskey: int
    id: int


@dataclass
class GameSpyProfileUpdateRequest(GameSpyRequest):
    """Changes some of the logged-in profile's details."""

    COMMAND = "updatepro"

    sesskey: int

    firstname: str | None = None
    lastname: str | None = None
    aim: str | None = None
    zipcode: str | None = None


@dataclass
class GameSpyStatusRequest(GameSpyRequest):
    """The console's online status."""

    COMMAND = "status"

    sesskey: int


REQUEST_TYPES: dict[str, type[GameSpyRequest]] = {
    request_type.COMMAND: request_type
    for request_type in (
        GameSpyKeepAliveRequest,
        GameSpyLoginRequest,
        GameSpyLogoutRequest,
        GameSpyProfileRequest,
        GameSpyProfileUpdateRequest,
        GameSpyStatusRequest,
    )
}
