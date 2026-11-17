"""Game Sync IDs."""
import binascii

GSCD_CHARTABLE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
GSCD_LENGTH = 10
BITS_PER_CHAR = 5
MAX_GSID = 0x7FFFFFFF


def _checksum(gsid: int) -> int:
    return binascii.crc_hqx(gsid.to_bytes(4, "little"), 0xFFFF)


def gsid_to_gscd(gsid: int) -> str:
    """Return the ten-character form of a numeric Game Sync ID."""
    value = gsid | (_checksum(gsid) << 32)
    return "".join(GSCD_CHARTABLE[(value >> (BITS_PER_CHAR * i)) & 0x1F] for i in range(GSCD_LENGTH))


def _decode(gscd: str) -> int:
    """Decode a gscd to a number.

    The gsid is in the low 32 bits, then the checksum. Raise ValueError for a
    character outside the table.
    """
    value = 0
    for i, char in enumerate(gscd):
        value |= GSCD_CHARTABLE.index(char) << (BITS_PER_CHAR * i)
    return value


def gscd_to_gsid(gscd: str) -> int:
    """Return the numeric Game Sync ID in a gscd."""
    return _decode(gscd) & 0xFFFFFFFF


def is_valid_gscd(gscd: str | None) -> bool:
    """Whether `gscd` is ten valid characters with a matching checksum."""
    if gscd is None or len(gscd) != GSCD_LENGTH:
        return False

    try:
        value = _decode(gscd)
    except ValueError:
        return False

    gsid = value & 0xFFFFFFFF
    checksum = (value >> 32) & 0xFFFF
    return gsid <= MAX_GSID and _checksum(gsid) == checksum
