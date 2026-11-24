"""tools.lib.ppc: instruction encoders, the Asm assembler, prologue/epilogue."""
import struct

import pytest

from tools.lib import ppc
from tools.lib.dol import encode_branch
from tools.lib.ppc import (
    BLR, LWZ, MFLR, MTLR, STW, STWU, Asm, epilogue, ha, i_add, i_addi, i_addis, i_cmplwi, i_cmpwi,
    i_extsb, i_extsh, i_li, i_mem, i_mr, i_mulli, i_rlwinm, i_slwi, i_subf, lo, prologue,
)


def words(blob):
    return list(struct.unpack(f">{len(blob) // 4}I", blob))


def sign16(v):
    return v - 0x10000 if v & 0x8000 else v


def fields(word):
    """(opcode, rD/rS, rA, rB/imm low bits, XO) of a D/X-form word."""
    return word >> 26, (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31, (word >> 1) & 0x3FF


# Real instruction words from the patch scripts (checked 2026-11-24).
@pytest.mark.parametrize("word, expected", [
    (i_li(3, 2), 0x38600002),                      # apply_boo_day_orbs_patch.HOOK_WORD
    (i_mem(LWZ, 0, 31, 0x374), 0x801F0374),        # apply_whatgoesup_battle_patch.SITE_A_OLD
    (i_mem(STWU, 1, 1, -0x30), 0x9421FFD0),        # apply_cpu_landing_patch.HOOK_ORIGINAL
    (MFLR(0), 0x7C0802A6),
    (MTLR(0), 0x7C0803A6),
    (BLR, 0x4E800020),
    (ppc.i_lis(3, 0x8028), 0x3C608028),             # lis r3,0x8028: apply_cpu_landing_patch.SELECT_HOOK_ORIGINAL
    (ppc.i_ori(3, 3, 0x1234), 0x60631234),
    # i_mr is the `ori ra,rs,0` form. The game's compiler emits `or ra,rs,rs` (0x7F43D378 for
    # mr r3,r26); both copy the register, but the words differ.
    (i_mr(3, 26), 0x63430000),
])
def test_known_words(word, expected):
    assert word == expected


def test_anchor_words_match_patch_constants():
    from tools.patches import apply_boo_day_orbs_patch, apply_cpu_landing_patch, apply_whatgoesup_battle_patch
    assert apply_boo_day_orbs_patch.HOOK_WORD == i_li(3, 2)
    assert apply_whatgoesup_battle_patch.SITE_A_OLD == struct.pack(">I", i_mem(LWZ, 0, 31, 0x374))
    assert apply_cpu_landing_patch.HOOK_ORIGINAL == i_mem(STWU, 1, 1, -0x30)


@pytest.mark.parametrize("address", [0x80000000, 0x80007FFC, 0x80008000, 0x8000FFFF, 0x802F49A0, 0x8017E03C])
def test_ha_lo_rebuild_address(address):
    assert ((ha(address) << 16) + sign16(lo(address))) & 0xFFFFFFFF == address


def test_ha_rounds_up_when_lo_is_negative():
    assert ha(0x80008000) == 0x8001 and sign16(lo(0x80008000)) == -0x8000


@pytest.mark.parametrize("n", [1, 2, 3, 4, 8, 16, 24, 31])
def test_slwi_is_rlwinm(n):
    # two definitions were merged on this equivalence
    assert i_slwi(5, 6, n) == i_rlwinm(5, 6, n, 0, 31 - n)


@pytest.mark.parametrize("word, expected", [
    (i_add(3, 4, 5), (31, 3, 4, 5, 266)),
    (i_subf(3, 4, 5), (31, 3, 4, 5, 40)),
    (i_extsh(3, 4), (31, 4, 3, 0, 922)),   # X-form with rS in the rD slot: extsh rA, rS
    (i_extsb(3, 4), (31, 4, 3, 0, 954)),
])
def test_x_form_fields(word, expected):
    assert fields(word) == expected


@pytest.mark.parametrize("word, opcode, rd, ra, imm", [
    (i_cmpwi(7, -1), 11, 0, 7, -1),
    (i_cmplwi(7, 0x80), 10, 0, 7, 0x80),
    (i_addis(3, 4, 0x8030), 15, 3, 4, sign16(0x8030)),
    (i_mulli(3, 4, 0x7C), 7, 3, 4, 0x7C),
    (i_addi(1, 1, -0x20), 14, 1, 1, -0x20),
])
def test_d_form_fields(word, opcode, rd, ra, imm):
    assert word >> 26 == opcode
    assert (word >> 21) & 31 == rd   # cr field 0, L = 0 for the compares
    assert (word >> 16) & 31 == ra
    assert sign16(word & 0xFFFF) == imm


def test_asm_forward_and_backward_labels():
    a = Asm(0x80001000)
    a.label("top")
    a.word(0x60000000)
    a.branch("b", "end")      # forward: +8
    a.branch("b", "top")      # backward: -8
    a.label("end")
    a.word(BLR)
    out = words(a.assemble())
    assert out == [0x60000000, 0x48000008, 0x4BFFFFF8, BLR]
    assert a.labels == {"top": 0x80001000, "end": 0x8000100C}


@pytest.mark.parametrize("kind, bo, bi", [
    ("beq", 12, 2), ("bne", 4, 2), ("blt", 12, 0), ("bge", 4, 0), ("ble", 4, 1), ("bgt", 12, 1),
])
@pytest.mark.parametrize("forward", [True, False])
def test_asm_conditional_branches(kind, bo, bi, forward):
    a = Asm(0x80002000)
    if not forward:
        a.label("t")
        a.word(0)
        a.word(0)
    a.branch(kind, "t")
    if forward:
        a.word(0)
        a.label("t")
    out = words(a.assemble())
    word = out[-1] if not forward else out[0]
    displacement = sign16(word & 0xFFFC)
    assert word >> 26 == 16
    assert (word >> 21) & 31 == bo
    assert (word >> 16) & 31 == bi
    assert word & 3 == 0          # no AA, no LK
    assert displacement == (8 if forward else -8)


def test_asm_call_matches_encode_branch():
    a = Asm(0x80003000)
    a.word(0)
    a.call(0x8017E03C)
    assert words(a.assemble())[1] == encode_branch(0x80003004, 0x8017E03C, True)


def test_asm_length_is_four_bytes_per_word():
    a = Asm(0x80003000)
    for _ in range(5):
        a.word(0)
    a.label("x")              # labels take no space
    a.branch("beq", "x")
    a.call(0x80003000)
    assert len(a.assemble()) == 4 * 7


def test_asm_unknown_label_raises():
    a = Asm(0x80003000)
    a.branch("b", "missing")
    with pytest.raises(KeyError):
        a.assemble()


def test_prologue_epilogue():
    a = Asm(0x80004000)
    prologue(a, 0x20, (30, 31))
    epilogue(a, 0x20, (30, 31))
    out = words(a.assemble())
    assert out[:5] == [
        i_mem(STWU, 1, 1, -0x20),
        MFLR(0),
        i_mem(STW, 0, 1, 0x24),       # LR save slot in the caller's frame
        i_mem(STW, 30, 1, 0x18),      # r30, r31 just below the back chain at frame
        i_mem(STW, 31, 1, 0x1C),
    ]
    assert out[5:] == [
        i_mem(LWZ, 0, 1, 0x24),
        i_mem(LWZ, 30, 1, 0x18),
        i_mem(LWZ, 31, 1, 0x1C),
        MTLR(0),
        i_addi(1, 1, 0x20),
        BLR,
    ]


def test_b_to_is_unlinked_branch():
    assert ppc.b_to(0x80001000, 0x80001010) == 0x48000010


@pytest.mark.parametrize("word, expected", [
    (ppc.i_lwzx(3, 4, 5), (31, 3, 4, 5, 23)),
    (ppc.i_lbzx(3, 4, 5), (31, 3, 4, 5, 87)),
    (ppc.i_mullw(3, 4, 5), (31, 3, 4, 5, 235)),
    (ppc.i_divw(3, 4, 5), (31, 3, 4, 5, 491)),
    (ppc.i_cmpw(4, 5), (31, 0, 4, 5, 0)),
    (ppc.i_or(3, 4, 5), (31, 4, 3, 5, 444)),       # or rA, rS, rB: rS in the rD slot
    (ppc.i_srawi(3, 4, 2), (31, 4, 3, 2, 824)),
])
def test_more_x_form_fields(word, expected):
    assert fields(word) == expected


def test_or_form_is_the_games_mr():
    assert ppc.i_or(3, 26, 26) == 0x7F43D378        # mr r3,r26 as the compiler emits it


def test_rotate_and_float_encoders():
    assert ppc.i_clrlwi24(3, 4) == i_rlwinm(3, 4, 0, 24, 31)
    assert ppc.i_fadds(1, 2, 3) == 0xEC22182A       # fadds f1,f2,f3
    assert ppc.MTCTR(12) == 0x7D8903A6 and ppc.BCTR == 0x4E800420
