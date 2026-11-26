"""tools.lib.board_tables: the table and site readers, and the table list itself."""
import struct

import pytest

from tests.builders import make_dol
from tools.lib import board_tables as bt

BASE = 0x80200000
TERMINATED = bt.Table("t", "main.dol", BASE, ">ii", None, -1, 2, "", "")
COUNTED = bt.Table("c", "main.dol", BASE, ">I", 3, None, 3, "", "")


def dol_with(payload):
    return make_dol([("text", 0x80003100, b"\0" * 8), ("data", BASE, payload)])


def test_terminated_table_stops_at_terminator():
    dol = dol_with(struct.pack(">6i", 0, 10, 1, 11, -1, 0))
    assert bt.read_table(dol, TERMINATED) == [(0, 10), (1, 11)]


def test_counted_table_reads_count():
    dol = dol_with(struct.pack(">4I", 7, 8, 9, 0xFFFFFFFF))
    assert bt.read_table(dol, COUNTED) == [(7,), (8,), (9,)]


def test_missing_terminator_raises():
    dol = dol_with(struct.pack(">4i", 0, 10, 1, 11))
    with pytest.raises(ValueError, match="past the end|no terminator"):
        bt.read_table(dol, TERMINATED)


def test_counted_table_past_end_raises():
    dol = dol_with(struct.pack(">2I", 7, 8))
    with pytest.raises(ValueError, match="past the end"):
        bt.read_table(dol, COUNTED)


def make_rel(sections):
    """Minimal REL: header with the section table at 0x40, then each section's bytes."""
    header = bytearray(0x40 + 8 * len(sections))
    struct.pack_into(">I", header, 0x0C, len(sections))
    struct.pack_into(">I", header, 0x10, 0x40)
    body = bytearray()
    for index, data in enumerate(sections):
        if data:
            offset = len(header) + len(body)
            struct.pack_into(">II", header, 0x40 + 8 * index, offset | (index == 1), len(data))
            body += data
    return bytes(header + body)


def test_rel_table_and_site():
    text = bytes(0xCC) + struct.pack(">I", 0x38600003)
    rodata = bytes(0x7C) + struct.pack(">6I", *range(0x7B, 0x81))
    rel = make_rel([b"", text, b"", b"", rodata])
    dlls = next(t for t in bt.TABLES if t.name == "party_board_dlls")
    assert bt.read_table(rel, dlls) == [(n,) for n in range(0x7B, 0x81)]
    site = bt.Site("s", "w04Dll.rel", 0xCC, 0x38600003, "", section=1)
    assert bt.read_site(rel, site) == 0x38600003


def test_rel_missing_section_raises():
    with pytest.raises(ValueError, match="section 4"):
        bt.rel_section(make_rel([b"", b"text"]), 4)


def test_dol_string():
    dol = dol_with(b"dll/w01dll.rel\0pad")
    assert bt.dol_string(dol, BASE) == "dll/w01dll.rel"


def test_table_list_is_consistent():
    names = [t.name for t in bt.TABLES] + [s.name for s in bt.SITES]
    assert len(names) == len(set(names))
    for table in bt.TABLES:
        assert (table.count is None) != (table.end is None), table.name
        if table.count is not None:
            assert table.expected == table.count, table.name
        assert (table.file == "main.dol") == (table.section == 0), table.name
    assert all(s.word >> 26 in (10, 11, 14) for s in bt.SITES)   # cmpwi / cmplwi / li
