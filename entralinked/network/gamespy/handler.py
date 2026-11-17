"""A console's connection to the GameSpy server."""
import hashlib
import logging
import secrets
import socketserver

from ...context import Context
from ...model.user.game_profile import GameProfile
from ...model.user.user import User
from ...utility import credential_generator
from .codec import TERMINATOR, decode_request, encode_message
from .message import (
    GameSpyChallengeMessage,
    GameSpyErrorMessage,
    GameSpyLoginResponse,
    GameSpyMessage,
    GameSpyProfileResponse,
)
from .request import (
    GameSpyLoginRequest,
    GameSpyLogoutRequest,
    GameSpyProfileRequest,
    GameSpyProfileUpdateRequest,
    GameSpyRequest,
)

logger = logging.getLogger(__name__)

SERVICE = "gamespy"
IDLE_TIMEOUT_SECONDS = 180.0
SERVER_CHALLENGE_LENGTH = 10
NO_SESSION = -1


class GameSpyError:
    """Error codes of the GameSpy presence protocol."""

    INTERNAL = 0x100
    INVALID_PARTNER_TOKEN = 0x200
    INVALID_SESSION_KEY = 0x201
    INVALID_RESPONSE = 0x202


def create_credential_hash(challenge_hash: str, auth_token: str, first_challenge: str, second_challenge: str) -> str:
    """Return the proof sent by either the console or the server."""
    padding = " " * 48
    raw = f"{challenge_hash}{padding}{auth_token}{first_challenge}{second_challenge}{challenge_hash}"
    return hashlib.md5(raw.encode("UTF-8")).hexdigest()


class GameSpyHandler(socketserver.BaseRequestHandler):
    """Handles one connection. socketserver creates one per console."""

    def setup(self) -> None:
        """Send the server's challenge."""
        context: Context = self.server.context
        self.user_manager = context.user_manager

        self.session_key = NO_SESSION
        self.user: User | None = None
        self.profile: GameProfile | None = None

        self.server_challenge = credential_generator.generate_challenge(SERVER_CHALLENGE_LENGTH)
        self.send_message(GameSpyChallengeMessage(self.server_challenge, 1))

    def handle(self) -> None:
        """Read requests until the console disconnects or times out."""
        self.request.settimeout(IDLE_TIMEOUT_SECONDS)
        buffer = bytearray()

        try:
            while data := self.request.recv(512):
                buffer.extend(data)

                while TERMINATOR in buffer:
                    message, _, rest = buffer.partition(TERMINATOR)
                    buffer = rest
                    self.process(decode_request(bytes(message)))

        except (TimeoutError, ConnectionResetError, ConnectionAbortedError):
            logger.info("User %s timed out or connection was reset", self._user_label())

        except Exception:
            logger.exception("Exception caught in GameSpy handler")
            self.send_error(GameSpyError.INTERNAL, "An internal error occurred on the server.", fatal=True)

    def finish(self) -> None:
        """Clean up when the connection is over."""
        logger.info("User %s disconnected from GameSpy server", self._user_label())

    def _user_label(self) -> str | None:
        return self.user.redacted_id if self.user else None

    def process(self, request: GameSpyRequest) -> None:
        """Check the session key if the request needs one, then act on the request."""
        sequence_id = getattr(request, "id", 0)

        if request.NEEDS_SESSION:
            session_key = getattr(request, "sesskey", NO_SESSION)
            if self.session_key == NO_SESSION or session_key != self.session_key:
                self.send_error(GameSpyError.INVALID_SESSION_KEY, "Invalid session key.", sequence_id)
                return

        if isinstance(request, GameSpyLoginRequest):
            self.handle_login(request)
        elif isinstance(request, GameSpyLogoutRequest):
            logger.info("User %s logged out", self._user_label())
            self.session_key = NO_SESSION
        elif isinstance(request, GameSpyProfileRequest):
            self.handle_get_profile(request)
        elif isinstance(request, GameSpyProfileUpdateRequest):
            self.handle_update_profile(request)
        # keep-alive and status requests need no answer

    def handle_login(self, request: GameSpyLoginRequest) -> None:
        """Verify the console's response and start a session."""
        session = self.user_manager.get_service_session(request.authtoken, SERVICE)

        if session is None or session.branch_code is None:
            logger.info("Rejecting GameSpy login request because the partner token is invalid")
            self.send_error(GameSpyError.INVALID_PARTNER_TOKEN, "Invalid partner token.", request.id)
            return

        expected_response = create_credential_hash(
            session.challenge_hash, request.authtoken, request.challenge, self.server_challenge)

        if expected_response != request.response:
            logger.info("Rejecting GameSpy login request because the challenge response is invalid")
            self.send_error(GameSpyError.INVALID_RESPONSE, "Invalid response.", request.id)
            return

        profile = self.user_manager.create_profile_for_user(session.user, session.branch_code)

        self.user = session.user
        self.profile = profile
        self.session_key = secrets.randbits(31)
        logger.info("User %s logged in with profile %s", self.user.redacted_id, profile.id)

        proof = create_credential_hash(
            session.challenge_hash, request.authtoken, self.server_challenge, request.challenge)
        self.send_message(GameSpyLoginResponse(self.user.id, profile.id, proof, self.session_key, request.id))

    def handle_get_profile(self, request: GameSpyProfileRequest) -> None:
        """Send the logged-in profile."""
        profile = self.profile
        assert profile is not None

        self.send_message(GameSpyProfileResponse(
            profile.id, profile.firstname, profile.lastname, profile.aim, profile.zipcode, "signature", request.id))

    def handle_update_profile(self, request: GameSpyProfileUpdateRequest) -> None:
        """Store the profile details the console sent, if any of them changed."""
        profile, user = self.profile, self.user
        assert profile is not None and user is not None

        changed = False
        for name in ("firstname", "lastname", "aim", "zipcode"):
            value = getattr(request, name)
            if value is not None and value != getattr(profile, name):
                setattr(profile, name, value)
                changed = True

        if changed:
            self.user_manager.save_user(user)

    def send_message(self, message: GameSpyMessage) -> None:
        """Send a message."""
        try:
            self.request.sendall(encode_message(message))
        except OSError:
            logger.exception("Failed to send GameSpy message")

    def send_error(self, error_code: int, error_message: str, sequence_id: int = 0, fatal: bool = False) -> None:
        """Send an error message."""
        self.send_message(GameSpyErrorMessage(error_code, error_message, int(fatal), sequence_id))
