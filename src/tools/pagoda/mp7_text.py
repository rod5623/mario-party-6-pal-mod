"""Mario Party 7 message records -> Mario Party 6 records, for Pagoda Peak's text (MP7 bank 0x14).

Both games use the same text codes (0x10 space, 0x0A new line, 0xFF page break, 0x0F choice, 0x85 ellipsis,
0x1E colour and 0x1F insert pairs, 4-space indents). Two things differ:
  * The 4-byte record header. MP7 writes 00FF 00FF everywhere. MP6 gives the window size: plain text
    is (21, max(3, lines on the fullest page)) and a choice is (18, lines), as in its board banks.
  * Icon 0x0E 0x13: MP7's coin icon in "Yes [coin] x 10". MP6's font has another icon there, so it is
    dropped.
"""
import struct

MP7_HEADER = b"\x00\xff\x00\xff"
TEXT_WIDTH, CHOICE_WIDTH, MIN_LINES = 21, 18, 3
COIN_ICON = b"\x0e\x13"


def header(body):
    """MP6's window size for a record body."""
    text = body.rstrip(b"\0")
    pages = [page for page in text.split(b"\xff") if page] or [b""]
    lines = max(page.rstrip(b"\n").count(b"\n") + 1 for page in pages)
    if b"\x0f" in text:
        return struct.pack(">HH", CHOICE_WIDTH, lines)
    return struct.pack(">HH", TEXT_WIDTH, max(MIN_LINES, lines))


def convert(record):
    """An MP6 record (header, body, padded to 4 bytes) from an MP7 record."""
    if record[:4] != MP7_HEADER:
        raise ValueError(f"not an MP7 record header: {record[:4].hex()}")
    body = record[4:].rstrip(b"\0").replace(COIN_ICON, b"") + b"\0"
    out = header(body) + body
    return out + b"\0" * (-len(out) % 4)


def bank_records(data, bank):
    """The records of one bank of a messdata*.bin file, as bytes."""
    count = struct.unpack_from(">I", data, 0)[0]
    start = 4 + struct.unpack_from(">I", data, 4 + 4 * bank)[0]
    end = 4 + struct.unpack_from(">I", data, 4 + 4 * (bank + 1))[0] if bank + 1 < count else len(data)
    n = struct.unpack_from(">I", data, start)[0]
    offsets = [start + 4 + o for o in struct.unpack_from(f">{n}I", data, start + 4)] + [end]
    return [bytes(data[offsets[i]:offsets[i + 1]]) for i in range(n)]
