"""Nintendo WFC accounts and the sessions of logged-in consoles."""
import hashlib
import logging
import random
import re
import secrets
import threading
from dataclasses import asdict
from datetime import datetime, timedelta

from ...utility import credential_generator
from ...utility.db_manager import db
from .game_profile import GameProfile
from .service import ServiceSession
from .user import User

logger = logging.getLogger(__name__)

USER_ID_PATTERN = re.compile("[0-9]{13}")
SESSION_LIFETIME = timedelta(minutes=30)
AUTH_TOKEN_BYTES = 96
CHALLENGE_LENGTH = 8
MAX_PROFILE_ID = 2**31 - 1


def is_valid_user_id(user_id: str) -> bool:
    """Whether `user_id` looks like a WFC user id (13 digits)."""
    return bool(USER_ID_PATTERN.fullmatch(user_id))


class UserManager:
    """Keep every user in memory and save changes to the database."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.users: dict[str, User] = {}
        self.service_sessions: dict[str, ServiceSession] = {}

        for data in db.get_all_wfc_users():
            profiles = {branch_code: GameProfile(**profile) for branch_code, profile in data["profiles"].items()}
            self.users[data["id"]] = User(data["id"], data["password"], profiles)

        logger.info("Loaded %d user(s)", len(self.users))

    def save_user(self, user: User) -> None:
        """Write a user and its profiles to the database."""
        db.save_wfc_user(
            user_id=user.id,
            password=user.password,
            profiles={branch_code: asdict(profile) for branch_code, profile in user.profiles.items()},
        )

    def does_user_exist(self, user_id: str) -> bool:
        """Whether a user id is registered."""
        return user_id in self.users

    def register_user(self, user_id: str, password: str) -> User | None:
        """Create a user. Return None if the id is taken."""
        with self._lock:
            if user_id in self.users:
                logger.warning("Attempted to register user with duplicate ID: %s", user_id)
                return None

            user = User(user_id, password)
            self.save_user(user)
            self.users[user_id] = user
            return user

    def authenticate_user(self, user_id: str, password: str) -> User | None:
        """Return the user with this id, if the password matches."""
        user = self.users.get(user_id)
        return user if user is not None and user.password == password else None

    def create_profile_for_user(self, user: User, branch_code: str) -> GameProfile:
        """Return the user's profile, creating it if needed."""
        with self._lock:
            profile = user.profiles.get(branch_code)
            if profile is None:
                profile = GameProfile(random.randint(0, MAX_PROFILE_ID))
                user.profiles[branch_code] = profile
                self.save_user(user)
            return profile

    def create_service_session(self, user: User, service: str, branch_code: str | None = None) -> tuple[str, str]:
        """Let `user` log in to `service` for the next SESSION_LIFETIME.

        Return the token and challenge to send to the console.
        """
        auth_token = "NDS" + secrets.token_urlsafe(AUTH_TOKEN_BYTES)
        challenge = credential_generator.generate_challenge(CHALLENGE_LENGTH)
        challenge_hash = hashlib.md5(challenge.encode("UTF-8")).hexdigest()
        session = ServiceSession(user, service, branch_code, challenge_hash, datetime.now() + SESSION_LIFETIME)

        with self._lock:
            for token in [token for token, old in self.service_sessions.items() if old.has_expired()]:
                del self.service_sessions[token]
            self.service_sessions[auth_token] = session

        return auth_token, challenge

    def get_service_session(self, auth_token: str | None, service: str) -> ServiceSession | None:
        """Return the token's session, if it is still valid and is for `service`."""
        if auth_token is None:
            return None

        with self._lock:
            session = self.service_sessions.get(auth_token)

            if session is None:
                return None

            if session.has_expired():
                del self.service_sessions[auth_token]
                return None

        return session if session.service == service else None
