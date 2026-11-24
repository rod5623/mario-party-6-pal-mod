"""tools.lib.dol: address mapping, branches, safe byte patches and asm-listing edits."""
import struct

import pytest

from tests.builders import make_dol
from tools.lib.dol import (
    dol_offset, encode_branch, patch_asm_instruction, patch_asm_word, patch_dol_instruction,
    patch_word_table, replace_bytes, write_cave,
)


def sample_dol():
    return make_dol([
        ("text", 0x80003100, bytes(0x40)),
        ("text", 0x80005000, bytes(range(0x20))),
        ("data", 0x80200000, bytes(0x10)),
    ])


# The real bl words of apply_dk_bonus_patch.HOOKS.
@pytest.mark.parametrize("source, target, word", [
    (0x801BC87C, 0x8017E03C, 0x4BFC17C1),
    (0x801BC898, 0x801E705C, 0x4802A7C5),
])
def test_encode_branch_known_words(source, target, word):
    assert encode_branch(source, target, link=True) == word


def test_encode_branch_matches_dk_bonus_hooks():
    from tools.patches.apply_dk_bonus_patch import HOOKS
    assert HOOKS[0x801BC87C][0] == encode_branch(0x801BC87C, 0x8017E03C, True)
    assert HOOKS[0x801BC898][0] == encode_branch(0x801BC898, 0x801E705C, True)


def test_encode_branch_unlinked():
    assert encode_branch(0x80001000, 0x80000FF0) == 0x4BFFFFF0


@pytest.mark.parametrize("displacement, ok", [
    (0x1FFFFFC, True), (0x2000000, False), (-0x2000000, True), (-0x2000004, False), (2, False),
])
def test_encode_branch_range(displacement, ok):
    source = 0x81000000
    if ok:
        word = encode_branch(source, source + displacement)
        assert word >> 26 == 18
    else:
        with pytest.raises(ValueError):
            encode_branch(source, source + displacement)


def test_dol_offset_maps_text_and_data():
    dol = sample_dol()
    assert dol_offset(dol, 0x80003100) == 0x100
    assert dol_offset(dol, 0x8000313C) == 0x13C
    assert dol_offset(dol, 0x80005004) == 0x144
    assert dol[dol_offset(dol, 0x80005004)] == 4
    assert dol_offset(dol, 0x8020000C) == 0x16C


@pytest.mark.parametrize("address", [0x80003140, 0x80005020, 0x80200010, 0x80000000, 0x80004000])
def test_dol_offset_outside_sections(address):
    with pytest.raises(ValueError):
        dol_offset(sample_dol(), address)


def test_replace_bytes():
    data = bytearray(b"\x11\x22\x33\x44\x55")
    replace_bytes(data, 1, b"\x22\x33", b"\xAA\xBB", "test")
    assert data == b"\x11\xAA\xBB\x44\x55"
    replace_bytes(data, 1, b"\x22\x33", b"\xAA\xBB", "test")       # re-run: unchanged
    assert data == b"\x11\xAA\xBB\x44\x55"
    with pytest.raises(RuntimeError):
        replace_bytes(data, 2, b"\x22\x33", b"\xAA\xBB", "test")


def test_patch_dol_instruction():
    dol = sample_dol()
    patch_dol_instruction(dol, 0x80005004, b"\x04\x05\x06\x07", b"\x60\0\0\0", "nop")
    assert dol[0x144:0x148] == b"\x60\0\0\0"


def test_write_cave():
    dol = sample_dol()
    code = b"\x38\x60\x00\x02\x4E\x80\x00\x20"
    write_cave(dol, 0x80003110, code)
    assert dol[0x110:0x118] == code
    write_cave(dol, 0x80003110, code)                 # identical code is accepted
    with pytest.raises(RuntimeError):
        write_cave(dol, 0x80003110, b"\x60\0\0\0" * 2)
    with pytest.raises(RuntimeError):
        write_cave(dol, 0x80005000, code)             # not zeros


# Line shapes copied from a dtk listing (build/GP6P01/asm/*.s).
TEXT_LISTING = (
    "/* 801BC6CC 001B946C  2C 00 00 00 */\tcmpwi r0, 0x0\n"
    "/* 801BC6D0 001B9470  41 80 01 D0 */\tblt .L_801BC8A0\n"
    "/* 801BC6D4 001B9474  38 60 00 00 */\tli r3, 0x0\n"
)
INIT_LISTING = (
    "/* 80003610 00000610  43 00 00 00 */\t.4byte 0x43000000 /* illegal: bc 24, lt, 0x0 */\n"
    "/* 80003614 00000614  00 00 00 00 */\t.4byte 0x00000000 /* invalid */\n"
    "/* 80003618 00000618  00 00 00 00 */\t.4byte 0x00000000 /* invalid */\n"
)


def test_patch_asm_instruction():
    args = (0x801BC6D4, bytes.fromhex("38600000"), bytes.fromhex("38600002"), "li r3, 0x0", "li r3, 0x2")
    patched = patch_asm_instruction(TEXT_LISTING, *args)
    assert "/* 801BC6D4 001B9474  38 60 00 02 */\tli r3, 0x2\n" in patched
    assert patched.count("\n") == 3
    assert patch_asm_instruction(patched, *args) == patched
    with pytest.raises(RuntimeError):
        patch_asm_instruction(TEXT_LISTING, 0x801BC6D0, *args[1:])     # different instruction
    with pytest.raises(RuntimeError):
        patch_asm_instruction(TEXT_LISTING, 0x80000000, *args[1:])     # no such line


def test_patch_asm_word():
    patched = patch_asm_word(INIT_LISTING, 0x80003614, 0x4E800020, "blr")
    assert "/* 80003614 00000614  4E 80 00 20 */\t.4byte 0x4E800020 /* blr */\n" in patched
    assert patched.replace("4E 80 00 20", "00 00 00 00").replace(
        ".4byte 0x4E800020 /* blr */", ".4byte 0x00000000 /* invalid */") == INIT_LISTING
    assert patch_asm_word(patched, 0x80003614, 0x4E800020, "blr") == patched
    # another non-zero word is refused unless it is listed in `allowed` (or allowed=None)
    with pytest.raises(RuntimeError):
        patch_asm_word(patched, 0x80003614, 0x60000000, "nop")
    assert "0x60000000 /* nop */" in patch_asm_word(patched, 0x80003614, 0x60000000, "nop", allowed=(0x4E800020,))
    assert "0x60000000 /* nop */" in patch_asm_word(patched, 0x80003614, 0x60000000, "nop", allowed=None)


def test_patch_asm_word_rejects_instruction_lines():
    with pytest.raises(RuntimeError):
        patch_asm_word(TEXT_LISTING, 0x801BC6D4, 0x4E800020, "blr")


DATA_LISTING = (
    ".obj lbl_802DD648, global\n"
    "\t.4byte 0x00010304\n"
    "\t.4byte 0xFF000000\n"
    ".endobj lbl_802DD648\n"
    ".obj lbl_802DD650, global\n"
    "\t.4byte 0x00010304\n"
    ".endobj lbl_802DD650\n"
)


def test_patch_word_table():
    start, end = ".obj lbl_802DD648, global", ".endobj lbl_802DD648"
    original, new = [0x00010304, 0xFF000000], [0x00010203, 0x04FF0000]
    patched = patch_word_table(DATA_LISTING, start, end, original, new)
    assert "\t.4byte 0x00010203\n\t.4byte 0x04FF0000\n" in patched
    assert patched.endswith(".obj lbl_802DD650, global\n\t.4byte 0x00010304\n.endobj lbl_802DD650\n")
    assert patch_word_table(patched, start, end, original, new) == patched
    with pytest.raises(RuntimeError):
        patch_word_table(DATA_LISTING, start, end, [1, 2], new)


def test_branch_word_layout():
    word = encode_branch(0x80003000, 0x80003100, True)
    assert struct.pack(">I", word) == b"\x48\x00\x01\x01"


def test_asm_edits_need_exactly_one_line():
    doubled = INIT_LISTING + INIT_LISTING
    with pytest.raises(RuntimeError):
        patch_asm_word(doubled, 0x80003614, 0x4E800020, "blr")
    with pytest.raises(RuntimeError):
        patch_asm_word(INIT_LISTING, 0x80000000, 0x4E800020, "blr")


def test_patch_asm_word_malformed_line():
    with pytest.raises(RuntimeError):
        patch_asm_word("/* 80003614 00000614  00 00 00 00 \t.4byte 0x00000000\n", 0x80003614, 0, "x")
