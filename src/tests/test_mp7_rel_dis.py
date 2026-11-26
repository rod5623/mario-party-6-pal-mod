"""mp7_rel_dis: function bounds, lis/low id search and call descriptions (no game files or capstone)."""
from tools.scripts.mp7_rel_dis import BLR, describe_call, function_bounds, high_low_refs

STWU = 0x9421FFF0          # stwu r1, -0x10(r1)
NOP = 0x60000000


def test_function_bounds_cover_early_returns():
    words = [NOP, STWU, NOP, BLR, NOP, BLR, STWU, NOP, BLR]   # function 1 has two blr, function 2 follows
    assert function_bounds(words, 2) == (1, 6)
    assert function_bounds(words, 4) == (1, 6)
    assert function_bounds(words, 7) == (6, 9)                # the last function runs to the end


def test_high_low_refs():
    lis_r4 = 0x3C800014                                      # lis r4, 0x14
    words = [
        lis_r4, 0x38840007,                                  # addi r4, r4, 7      -> 0x140007
        lis_r4, 0x38A00008, 0x6084002B,                       # li r5, 8; ori r4, r4, 0x2b -> 0x14002b
        0x3C600014, 0x3863FFFF,                               # lis r3, 0x14; addi r3, r3, -1 -> 0x13ffff
        0x3C800015, 0x38840001,                               # another high half: ignored
        lis_r4, NOP,                                          # no low half in the window
    ]
    assert high_low_refs(words, 0x14) == {0x140007: [0], 0x14002B: [2], 0x13FFFF: [5]}


def test_describe_call():
    names = {0x8016B36C: "mbWinCreate"}
    matched = {0x80173E14: ("near", 0x8016B36C, 0.958), 0x8016349C: ("missing", 0x80164CFC, 0.59)}
    assert describe_call(0x80173E14, matched, names) == "MP7 0x80173e14 -> MP6 0x8016b36c mbWinCreate (near 0.96)"
    assert describe_call(0x8016349C, matched, names) == "MP7 0x8016349c -> MP6 missing"
    assert describe_call(0x80000000, matched, names) == "MP7 0x80000000 -> MP6 missing"
    assert describe_call(0x80173E14, matched, {}) == "MP7 0x80173e14 -> MP6 0x8016b36c (near 0.96)"
