r"""The GameSpy wire format. Backslash-separated keys and values ending in `\final\`.

    \login\\challenge\abc\authtoken\NDS...\id\1\final\

The first key usually has an empty value.
"""
from dataclasses import asdict, fields
from typing import get_type_hints

from .message import GameSpyMessage
from .request import REQUEST_TYPES, GameSpyRequest

SEPARATOR = "\\"
TERMINATOR = b"\\final\\"


def encode_message(message: GameSpyMessage) -> bytes:
    """Encode a message as bytes."""
    parts = [message.NAME, message.VALUE]

    for key, value in asdict(message).items():
        if value is not None:
            parts += [key, str(value)]

    return (SEPARATOR + SEPARATOR.join(parts)).encode("UTF-8") + TERMINATOR


def decode_request(data: bytes) -> GameSpyRequest:
    """Parse a request (without its terminator).

    Raise ValueError if it is malformed, is of an unknown type, or lacks a field the
    type requires.
    """
    text = data.decode("UTF-8", errors="ignore")

    if not text.startswith(SEPARATOR):
        raise ValueError(f"Was expecting '\\', got '{text[:1] or 'EOF'}'.")

    parts = text[1:].split(SEPARATOR)
    command = parts[0]
    request_type = REQUEST_TYPES.get(command)

    if request_type is None:
        raise ValueError(f"Invalid or unimplemented request type '{command}'")

    raw_fields = dict(zip(parts[2::2], parts[3::2], strict=False))
    kwargs: dict[str, str | int] = {}
    types = get_type_hints(request_type)  # everything arrives as text

    for field in fields(request_type):
        if field.name in raw_fields:
            raw_value = raw_fields[field.name]
            kwargs[field.name] = int(raw_value) if types[field.name] is int else raw_value

    try:
        return request_type(**kwargs)
    except TypeError as e:
        raise ValueError(f"Incomplete '{command}' request: {e}") from e
