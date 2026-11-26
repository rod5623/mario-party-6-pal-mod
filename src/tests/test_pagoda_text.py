"""tools.pagoda.mp7_text: MP7 message records converted to MP6 records."""
import struct

import pytest

from tools.pagoda import mp7_text


def mp7_record(body):
    raw = mp7_text.MP7_HEADER + body + b"\0"
    return raw + b"\0" * (-len(raw) % 4)


def test_plain_text_gets_mp6_window_size():
    one_line = mp7_text.convert(mp7_record(b"    Right\x10then\xc2\xff"))
    assert one_line[:4] == struct.pack(">HH", 21, 3)                     # at least 3 lines, like MP6
    four = mp7_text.convert(mp7_record(b"a\nb\nc\nd\xff"))
    assert four[:4] == struct.pack(">HH", 21, 4)
    pages = mp7_text.convert(mp7_record(b"a\nb\xffc\nd\ne\nf\nh\xff"))      # the fullest page counts
    assert pages[:4] == struct.pack(">HH", 21, 5)


def test_choice_and_coin_icon():
    body = b"    Buy\x10a\x10Star\xc3\n\n      \x0f\x10Yes  \x0e\x13\x10x\x10\x1f\x01\n      \x0f\x10No"
    out = mp7_text.convert(mp7_record(body))
    assert out[:4] == struct.pack(">HH", 18, 4)
    assert b"\x0e\x13" not in out and b"\x1f\x01" in out
    assert len(out) % 4 == 0 and out.rstrip(b"\0").endswith(b"No")


def test_rejects_other_headers():
    with pytest.raises(ValueError):
        mp7_text.convert(b"\x00\x15\x00\x03abc\0")


def test_bank_records():
    records = [mp7_record(b"one"), mp7_record(b"two\ntwo")]
    # record offsets count from just after the record count
    bank = struct.pack(">I", 2) + struct.pack(">2I", 8, 8 + len(records[0])) + b"".join(records)
    data = struct.pack(">I", 2) + struct.pack(">2I", 8, 8 + 16) + b"\0" * 12 + b"\0" * 4 + bank
    assert mp7_text.bank_records(data, 1) == records
