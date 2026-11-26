"""tools.pagoda.spaces: making a Pagoda Peak-shaped MP7 space table ready for MP6."""
import struct

import pytest

from tools.pagoda import spaces as sp


def space(kind=0, flags=0, colour=1, links=(), x=0.0):
    head = struct.pack(">9f", x, 0, 0, 0, 0, 0, 1, 1, 1)
    return {"head": head, "type": kind, "flags": flags, "colour": colour, "links": list(links)}


def pagoda_like():
    """88 spaces in one trail: start 37 -> 27 -> ... -> summit 54 -> dead end 74, stand 73 off the summit."""
    special = {sp.START, sp.SUMMIT_EXIT_TO, sp.SUMMIT, 73, sp.SUMMIT_EXIT}
    trail = [sp.START, sp.SUMMIT_EXIT_TO] + [i for i in range(1, 89) if i not in special] + [sp.SUMMIT]
    spaces = {i: space(x=float(i)) for i in range(1, 89)}
    for here, onward in zip(trail, trail[1:]):
        spaces[here]["links"] = [onward]
    spaces[sp.START].update(type=sp.TYPE_START, colour=0)
    spaces[sp.SUMMIT].update(type=sp.TYPE_MP7_ONLY, flags=0x10000, colour=0, links=[sp.SUMMIT_EXIT, 73])
    spaces[73].update(type=sp.TYPE_SIDE, colour=0)
    spaces[sp.SUMMIT_EXIT].update(colour=0)
    spaces[5].update(flags=0x80000000, colour=11)
    return [spaces[i] for i in range(1, 89)]


def test_parse_and_build_round_trip():
    blob = sp.build(pagoda_like())
    assert sp.build(sp.parse(blob)) == blob
    assert len(blob) == 4 + 88 * 46 + 2 * sum(len(s["links"]) for s in pagoda_like())


def test_parse_rejects_trailing_bytes():
    with pytest.raises(ValueError):
        sp.parse(sp.build(pagoda_like()) + b"\0\0")


def test_convert_keeps_mp7_flags():
    spaces = sp.convert(pagoda_like())
    sp.check_converted(spaces)
    assert [s["flags"] for s in spaces] == [s["flags"] for s in pagoda_like()]
    assert spaces[sp.SUMMIT - 1]["type"] == 0
    assert spaces[4]["colour"] == 1
    assert spaces[sp.SUMMIT_EXIT - 1]["links"] == [sp.SUMMIT_EXIT_TO]
    assert [s["head"] for s in spaces] == [s["head"] for s in pagoda_like()]


def test_convert_rejects_another_layout():
    spaces = pagoda_like()
    spaces[sp.SUMMIT_EXIT - 1]["links"] = [1]
    with pytest.raises(RuntimeError, match="dead end"):
        sp.convert(spaces)
    spaces = pagoda_like()
    spaces[0]["type"] = sp.TYPE_START
    with pytest.raises(RuntimeError, match="start"):
        sp.convert(spaces)
    with pytest.raises(RuntimeError, match="88"):
        sp.convert(pagoda_like()[:87])


def test_check_converted_finds_a_dead_end():
    spaces = sp.convert(pagoda_like())
    spaces[sp.SUMMIT_EXIT - 1]["links"] = []
    with pytest.raises(AssertionError, match="dead end"):
        sp.check_converted(spaces)
