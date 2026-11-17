"""The form encoding of the Nintendo WFC servers (NAS and DLS).

The format is `key=value&key=value`, where every value is base64 with `*`, `.`,
and `-` standing in for `=`, `+`, and `/`.
"""
import base64
import binascii
from collections.abc import Mapping
from urllib.parse import quote, unquote_plus

_TO_WFC_BASE64 = str.maketrans("=+/", "*.-")
_FROM_WFC_BASE64 = str.maketrans("*.-", "=+/")


def decode_form(data: str) -> dict[str, str]:
    """Decode a form body. Raise ValueError if a value isn't valid base64."""
    fields = {}

    for pair in data.split("&"):
        key, separator, value = pair.partition("=")
        if not separator:
            continue

        try:
            decoded = base64.b64decode(unquote_plus(value).translate(_FROM_WFC_BASE64), validate=True)
        except binascii.Error as e:
            raise ValueError(f"Form value of '{key}' is not valid base64") from e

        fields[unquote_plus(key)] = decoded.decode("latin-1")

    return fields


def encode_form(fields: Mapping[str, object]) -> str:
    """Encode `fields` as a form body."""
    return "&".join(
        quote(key, safe="") + "=" + base64.b64encode(str(value).encode("latin-1")).decode("ascii").translate(_TO_WFC_BASE64)
        for key, value in fields.items()
    )
