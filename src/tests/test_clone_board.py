"""apply_clone_board_patch: the alias stubs, their layout and reach, and the board-number read list."""
import struct

from tools.lib import board_tables as bt
from tools.lib.dol import encode_branch
from tools.patches import apply_clone_board_patch as cb


def test_clrlwi27_matches_the_game():
    assert bt.clrlwi27(29, 0) == 0x541D06FE      # 0x8016DC74 clrlwi r29, r0, 27
    assert bt.clrlwi27(3, 7) == 0x54E306FE       # mdpartydll 0x30648 clrlwi r3, r7, 27


def test_alias_stub():
    assert cb.alias_stub(29, 0) == [
        0x541D06FE,   # clrlwi r29, r0, 27
        0x2B9D000B,   # cmplwi cr7, r29, 11
        0x4C9E0020,   # bnelr cr7
        0x3BA00003,   # li r29, 3
        0x4E800020,   # blr
    ]


def test_sound_stub():
    assert cb.sound_stub() == [
        0x7C7C1B78,   # mr r28, r3 (the displaced instruction)
        0x5460043E,   # clrlwi r0, r3, 16
        0x2B800070,   # cmplwi cr7, r0, 0x70
        0x4C9E0020,   # bnelr cr7
        0x3B80007E,   # li r28, 0x7E
        0x4E800020,   # blr
    ]


def test_section_layout():
    code = cb.section_code()
    assert code.startswith(cb.PATH + b"\0")
    assert len(code) == cb.STUBS - cb.CODE_BASE + cb.STUB_SIZE * len(cb.stub_pairs())
    assert len(code) <= cb.CODE_SIZE
    for rd, rs in cb.stub_pairs():
        at = cb.stub_address(rd, rs) - cb.CODE_BASE
        assert list(struct.unpack_from(">5I", code, at)) == cb.alias_stub(rd, rs)
    assert list(struct.unpack_from(">6I", code, cb.SOUND_STUB - cb.CODE_BASE)) == cb.sound_stub()


def test_every_dol_site_reaches_its_stub():
    for read in bt.BOARD_NO_READS:
        if read.file == "main.dol":
            encode_branch(read.where, cb.stub_address(read.rd, read.rs), link=True)   # raises if out of range
    encode_branch(cb.SOUND_SITE, cb.SOUND_STUB, link=True)


def test_board_no_reads_are_unique():
    keys = [(r.file, r.where) for r in bt.BOARD_NO_READS]
    assert len(keys) == len(set(keys))
    assert len({r.name for r in bt.BOARD_NO_READS}) == len(bt.BOARD_NO_READS)
    assert {r.file for r in bt.BOARD_NO_READS} == {"main.dol", "mdpartydll.rel", "mdpresultdll.rel"}
