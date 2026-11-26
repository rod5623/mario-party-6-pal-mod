"""apply_mp7_spaces_test_patch: converting a Pagoda Peak-shaped space table to Snowflake Lake's meanings."""
import struct

import pytest

from tools.patches.test_aids import apply_mp7_spaces_test_patch as aid


def space(kind=0, flags=0, colour=1, links=(), x=0.0):
    head = struct.pack(">9f", x, 0, 0, 0, 0, 0, 1, 1, 1)
    return {"head": head, "type": kind, "flags": flags, "colour": colour, "links": list(links)}


def pagoda_like():
    """88 spaces in one trail: start 37 -> 27 -> ... -> summit 54 -> dead end 74, stand 73 off the summit."""
    special = {aid.START, aid.SUMMIT_EXIT_TO, aid.SUMMIT, 73, aid.SUMMIT_EXIT}
    trail = [aid.START, aid.SUMMIT_EXIT_TO] + [i for i in range(1, 89) if i not in special] + [aid.SUMMIT]
    spaces = {i: space(x=float(i)) for i in range(1, 89)}
    for here, onward in zip(trail, trail[1:]):
        spaces[here]["links"] = [onward]
    spaces[aid.START].update(type=aid.TYPE_START, colour=0)
    spaces[aid.SUMMIT].update(type=aid.TYPE_MP7_ONLY, flags=0x10000, colour=0, links=[aid.SUMMIT_EXIT, 73])
    spaces[73].update(type=aid.TYPE_SIDE, colour=0)
    spaces[aid.SUMMIT_EXIT].update(colour=0)
    spaces[5].update(flags=0x80000000, colour=11)
    return [spaces[i] for i in range(1, 89)]


def packed_index(flags, mask):
    """fn_80177014: the bits of `flags` under `mask`, packed together."""
    out, bit = 0, 1
    for n in range(32):
        if mask & (1 << n):
            if flags & (1 << n):
                out |= bit
            bit <<= 1
    return out


def test_parse_and_build_round_trip():
    blob = aid.build(pagoda_like())
    assert aid.build(aid.parse(blob)) == blob
    assert len(blob) == 4 + 88 * 46 + 2 * sum(len(s["links"]) for s in pagoda_like())


def test_convert():
    spaces = aid.convert(pagoda_like())
    aid.check_converted(spaces)
    summit = spaces[aid.SUMMIT - 1]
    assert summit["flags"] == 0x80 and summit["type"] == 0
    assert [s["flags"] for i, s in enumerate(spaces, 1) if i != aid.SUMMIT] == [0] * 87
    assert spaces[4]["colour"] == 1
    assert spaces[aid.SUMMIT_EXIT - 1]["links"] == [aid.SUMMIT_EXIT_TO]
    assert [s["head"] for s in spaces] == [s["head"] for s in pagoda_like()]


def test_convert_keeping_mp7_flags():
    spaces = aid.convert(pagoda_like(), mp7_flags=True)
    aid.check_converted(spaces, mp7_flags=True)
    assert [s["flags"] for s in spaces] == [s["flags"] for s in pagoda_like()]
    assert spaces[aid.SUMMIT - 1]["type"] == 0
    assert spaces[4]["colour"] == 1
    with pytest.raises(AssertionError):
        aid.check_converted(spaces)  # no Chomp station: Snowflake Lake's REL can't run this table


def test_convert_rejects_another_layout():
    spaces = pagoda_like()
    spaces[aid.SUMMIT_EXIT - 1]["links"] = [1]
    with pytest.raises(RuntimeError, match="dead end"):
        aid.convert(spaces)
    spaces = pagoda_like()
    spaces[0]["type"] = aid.TYPE_START
    with pytest.raises(RuntimeError, match="start"):
        aid.convert(spaces)
    with pytest.raises(RuntimeError, match="88"):
        aid.convert(pagoda_like()[:87])


def test_station_bits_match_the_engine():
    for index in range(1, 8):
        assert packed_index(aid.station_bits(index), aid.STATION_MASK) == index
    assert aid.station_bits(1) == 0x80 and aid.station_bits(3) == 0x180
    with pytest.raises(ValueError):
        aid.station_bits(8)


def test_rel_words():
    assert aid.ORIGINAL == 0x7F83E378                                   # or r3, r28, r28
    assert aid.PATCHED == (24 << 26) | (28 << 21) | (3 << 16) | aid.NEW_FILE
