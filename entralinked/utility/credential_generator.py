"""Random tokens and challenges for the Nintendo WFC login handshake."""
import secrets

CHALLENGE_CHARTABLE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"


def generate_challenge(length: int) -> str:
    """`length` random upper-case letters and digits."""
    return "".join(secrets.choice(CHALLENGE_CHARTABLE) for _ in range(length))

