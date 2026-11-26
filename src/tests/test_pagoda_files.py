"""Pagoda Peak's w07.bin: pagoda.h's FILE_* numbers match pagoda_board's file list, and the moved data dir table."""
import re
import struct

import pytest

from tools.lib.dol import dol_offset
from tools.lib.paths import ROOT
from tools.lib.ppc import ha, lo
from tools.patches import apply_pagoda_board_patch as board

SRC = ROOT / "src" / "REL" / "w07Dll"
HEADER = SRC / "pagoda.h"


def defines():
    return {m[1]: int(m[2]) for m in re.finditer(r"#define (FILE_\w+) (\d+)", HEADER.read_text())}


def test_header_numbers_match_the_archive():
    named = {f.name: i for i, f in enumerate(board.FILES) if f.name}
    assert defines() == named


def test_motion_tables_follow_their_models():
    """bowser.c and star.c list the motions as the files right after the model, as FILES stores them."""
    for source, table, model, count in (("bowser.c", "bowserMot", "FILE_BOWSER", 9),
                                        ("star.c", "koopaMot", "FILE_KOOPA", 5)):
        body = re.search(rf"{table}\[\] = \{{(.*?)\}};", (SRC / source).read_text(), re.S)[1]
        assert re.findall(rf"DIR_BOARD \| \({model} \+ (\d+)\)", body) == [str(n) for n in range(1, count + 1)]
        first = board.file_number(model)
        assert all(f.name is None for f in board.FILES[first + 1:first + 1 + count])
        assert board.FILES[first + 1 + count].name is not None


def test_dir_number_in_header():
    assert re.search(r"#define DIR_BOARD (0x[0-9A-F]+)", HEADER.read_text())[1] == f"0x{board.DIR_NO << 16:08X}"


def fake_dol(entries):
    """A one-section DOL holding the data dir table at DIR_TABLE, three lis/addi pairs at the references
    and room for section 19."""
    base = 0x80007000
    body = bytearray(board.DIR_TABLE + 8 * (board.DIR_COUNT + 1) - base)
    for i in range(entries):
        struct.pack_into(">Ii", body, board.DIR_TABLE - base + 8 * i, 0x80200000 + 0x10 * i, -1)
    for site in board.DIR_REFERENCES:
        struct.pack_into(">2I", body, site - base, 0x3C600000 | ha(board.DIR_TABLE),
                         0x38030000 | lo(board.DIR_TABLE))
    header = bytearray(0x100)
    struct.pack_into(">I", header, 0, 0x100)
    struct.pack_into(">I", header, 0x48, base)
    struct.pack_into(">I", header, 0x90, len(body))
    return header + body


def test_section_blob_appends_w07():
    dol = fake_dol(board.DIR_COUNT)
    blob = board.section_blob(dol)
    assert blob[:len(board.PATH) + 1] == board.PATH + b"\0"
    table = blob[board.NEW_TABLE - board.PATH_ADDR:]
    rows = [struct.unpack_from(">Ii", table, 8 * i) for i in range(board.DIR_COUNT + 2)]
    assert rows[board.DIR_NO] == (board.PATH_ADDR, -1)
    assert rows[0] == (0x80200000, -1) and rows[-1] == (0, 0)
    assert board.NEW_TABLE_END <= board.CODE_END


def test_section_blob_rejects_another_table():
    with pytest.raises(RuntimeError):
        board.section_blob(fake_dol(board.DIR_COUNT - 1))


def test_repoint_is_idempotent():
    dol = fake_dol(board.DIR_COUNT)
    for _ in range(2):
        for site in board.DIR_REFERENCES:
            board.repoint(dol, site)
    for site in board.DIR_REFERENCES:
        lis, addi = struct.unpack_from(">2I", dol, dol_offset(dol, site))
        assert ((lis & 0xFFFF) << 16) + struct.unpack(">h", struct.pack(">H", addi & 0xFFFF))[0] == board.NEW_TABLE


def test_base_reads_reach_the_moved_table():
    """The rewritten base-register reads load T+4 (entry numbers) or T (the path) plus the index register."""
    for site, (original, patched) in board.base_read_words().items():
        hi, lw = patched[1:] if site == board.PATH_READ else (patched[0], patched[2])
        target = ((hi & 0xFFFF) << 16) + struct.unpack(">h", struct.pack(">H", lw & 0xFFFF))[0]
        assert target == board.NEW_TABLE + (0 if site == board.PATH_READ else 4)
        assert original[-1] == board.LWZX_R3
    assert board.slwi(0, 20, 3) == 0x56801838


def test_message_bank_in_header():
    """PAGODA_MES(n) is MP7 record n in pagoda_board's bank."""
    value = re.search(r"#define PAGODA_MES\(n\) \((0x[0-9A-F]+) \+ \(n\)\)", HEADER.read_text())[1]
    assert int(value, 16) == board.BANK << 16


def test_orb_list_drops_the_snack():
    rows = [bytes([orb]) + bytes(15) for orb in (0x00, 0x1E, 0x05)] + [b"\xff" + bytes(15)]
    out = board.orb_list(b"".join(rows))
    assert [out[i] for i in range(0, len(out), 16)] == [0x00, 0x05, board.CANNON_ID, 0xFF]
    cannon = out[32:48]
    assert cannon[1:4] == bytes([10, 10, 10]) and cannon[4:] == bytes(board.CANNON_WEIGHTS)
    assert all(0 < w < 128 for w in board.CANNON_WEIGHTS)   # read as signed bytes (extsb)
    with pytest.raises(RuntimeError):
        board.orb_list(rows[0] + rows[3])


def test_label_stub_words():
    words = board.label_stub()
    assert words[0] == 0x3CA08028                    # lis r5, 0x8028
    assert words[1] == 0x88A53298                    # lbz r5, 0x3298(r5)
    assert words[3] == 0x2805000B                    # cmplwi r5, 11
    assert words[4] == 0x38A00006                    # li r5, 6
    assert words[-2:] == [0x7FC5F378, 0x4E800020]    # mr r5, r30; blr


def test_cannon_stubs():
    exec_stub, kill_stub = board.cannon_stubs()
    assert exec_stub[:2] == [0x3D808030, 0x818CAAA0]           # lis r12, 0x8030; lwz r12, -0x5560(r12)
    assert kill_stub[:2] == [0x3D808030, 0x818CAAA4]
    assert exec_stub[3] == 0x4182000C and len(exec_stub) == 7  # beq to the last word: b HuPrcEnd
    target = board.CANNON_EXEC_STUB + 24 + (((exec_stub[6] & 0x3FFFFFC) ^ 0x2000000) - 0x2000000)
    assert exec_stub[6] >> 26 == 18 and not exec_stub[6] & 3 and target == board.HU_PRC_END
    assert kill_stub[3] == 0x4D820020 and kill_stub[-2:] == [0x7D8903A6, 0x4E800420]


def test_cannon_rows():
    data, event = board.cannon_rows()
    assert data[0] == board.CANNON_MODEL == 0x140058 and data[1] == 0x14001C
    assert data[2] == 0x4B003A and data[3] == 0x4B0039 and data[6] == 10 and data[7] == 0x43000000
    assert event == (board.CANNON_EXEC_STUB, board.CANNON_KILL_STUB, 0, 2, 0, 0xFFFFFFFF, 0)


def test_cannon_hooks_match_the_header():
    text = HEADER.read_text()
    assert f"(*(void (**)(void))0x{board.CANNON_HOOKS:08X})" in text
    assert f"(*(void (**)(void))0x{board.CANNON_HOOKS + 4:08X})" in text


def test_com_stub():
    words = board.com_stub()
    assert words[:2] == [0x3D808030, 0x818CAAA8]                    # lis r12, 0x8030; lwz r12, -0x5558(r12)
    assert words[3] == 0x41820018 and words[7] == 0x4E800421       # beq to the last word; bctrl
    assert words[8] == 0x7C7E1B78                                  # mr r30, r3: the chance
    last = board.CANNON_COM_STUB + 4 * (len(words) - 1)
    assert last + (((words[-1] & 0x3FFFFFC) ^ 0x2000000) - 0x2000000) == board.COM_SWITCH_DEFAULT


def test_cannon_com_chances():
    assert len(board.CANNON_COM_CHANCES) == 11 and all(0 <= c <= 100 for c in board.CANNON_COM_CHANCES)
    assert board.CANNON_COM_HOOK == board.CANNON_HOOKS + 8
    assert f"(*(s32 (**)(s32, s32))0x{board.CANNON_COM_HOOK:08X})" in HEADER.read_text()
