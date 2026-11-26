"""apply_pagoda_peak_patch: the moved tables and the reference re-pointing, on a synthetic DOL."""
import struct

import pytest

from tests.builders import make_dol
from tools.lib.dol import dol_offset
from tools.patches import apply_pagoda_peak_patch as pp


def vanilla_dol(text=b"\0" * 8):
    music = b"".join(struct.pack(">4i", b, 13 + b, 14 + b, 1) for b in range(11)) + struct.pack(">4i", -1, 0, 0, 0)
    return make_dol([
        ("text", 0x80003100, text),
        ("data", pp.PAUSE_TABLE, struct.pack(">11I", *(0x50044 + i for i in range(11)))),
        ("data", pp.TELOP_TABLE, struct.pack(">27I", *(0x5004D + i for i in range(27)))),
        ("data", pp.MUSIC_TABLE, music),
        ("data", pp.WELCOME_TABLE, struct.pack(">6I", *(0x2C0000 + i for i in range(6)))),
    ])


def test_new_tables():
    blob = pp.new_tables(vanilla_dol())
    music = [struct.unpack_from(">4i", blob, 16 * i) for i in range(13)]
    assert music[10] == (10, 23, 24, 1)
    assert music[11] == (11, pp.TRACK, pp.TRACK, 1) and music[12][0] == -1
    at = pp.NEW_PAUSE - pp.TABLES_BASE
    pause = struct.unpack_from(">12I", blob, at)
    telop = struct.unpack_from(">28I", blob, pp.NEW_TELOP - pp.TABLES_BASE)
    welcome = struct.unpack_from(">12I", blob, pp.NEW_WELCOME - pp.TABLES_BASE)
    assert pause[:11] == tuple(0x50044 + i for i in range(11)) and pause[11] == pp.LOGO
    assert telop[:27] == tuple(0x5004D + i for i in range(27)) and telop[27] == pp.LOGO
    assert welcome[:6] == tuple(0x2C0000 + i for i in range(6))
    assert welcome[6:11] == (0x2C0000,) * 5 and welcome[11] == pp.WELCOME == 0x2C0013
    assert len(blob) == pp.TABLES_END - pp.TABLES_BASE


def test_new_tables_rejects_an_unexpected_music_table():
    dol = bytearray(vanilla_dol())
    struct.pack_into(">i", dol, dol_offset(dol, pp.MUSIC_TABLE + 16 * 11), 11)   # no terminator after 11 rows
    with pytest.raises(RuntimeError):
        pp.new_tables(dol)


def test_repoint_is_idempotent():
    lis = 0x3C600000 | 0x8026                      # lis r3, 0x8026
    addi = 0x38030000 | 0x51F8                     # addi r0, r3, 0x51F8
    dol = bytearray(vanilla_dol(struct.pack(">2I", lis, addi)))
    pp.repoint(dol, 0x80003100, pp.MUSIC_TABLE, pp.NEW_MUSIC)
    hi, low = struct.unpack_from(">2I", dol, dol_offset(dol, 0x80003100))
    assert (hi >> 16, low >> 16) == (0x3C60, 0x3803)                          # registers kept
    assert ((hi & 0xFFFF) << 16) + struct.unpack(">h", struct.pack(">H", low & 0xFFFF))[0] == pp.NEW_MUSIC
    before = bytes(dol)
    pp.repoint(dol, 0x80003100, pp.MUSIC_TABLE, pp.NEW_MUSIC)
    assert bytes(dol) == before


def test_tables_fit_after_the_clone_board_code():
    from tools.patches import apply_clone_board_patch as clone
    assert pp.TABLES_BASE >= clone.CODE_BASE + len(clone.section_code())
    assert pp.TABLES_END <= clone.CODE_END
    assert sum(len(sites) for _, sites in pp.REFERENCES.values()) == 20
    assert set(pp.OWN_READS) <= {r.name for r in pp.BOARD_NO_READS}
