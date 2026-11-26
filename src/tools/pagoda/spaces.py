"""Pagoda Peak's space table: MP7 data/w02.bin file 0, made ready for MP6's engine and the C board REL.

Both games use the same 46-byte space record (88 spaces here, LZ type 1). What the fields mean (research of
2026-11-24; the retired test aid mp7_spaces_test, kept in plans/pagoda-peak/retired/, has the full notes):
  * Type (u16 at +36, masu+0x10) is engine-wide and the same in both games: 0x8000 is the start (one
    colour-0 node per board; MP7 space 37), 0x8 -> 0x4 pairs are climbs, 0x20 is the shop model's node and
    0x2000 a side node (stands for board objects, event points). MP7 adds 0x100 (only on the summit, space
    54), which no MP6 code tests: cleared.
  * Flags (u32 at +38, masu+0x14) are board-defined, and kept: the C board finds its event spaces by MP7's
    own bits (pagoda.h MASU_*). The DOL only tests space flags against the board's mbBranchMAttrSet mask (0
    here) or a caller's argument, so the extra bits are safe for the engine.
  * Colour (u16 at +42) codes 0-10 match; MP6's colour tables (0x80265408 / 0x80265460) don't list 11 in both
    modes, so MP7's colour 11 (spaces 17 and 39) becomes blue.
  * The trail runs from the start (37) to the summit (54 -> 74, a dead end). Space 74 gets a link to 27, the
    first space after the start (star.c sends players back down; the link keeps the graph walkable).
  * MP7 picks file 0 (with file 1 as masu layer 1) in party mode: w02dll .text 0x124-0x194 tests GwSystem
    byte 0 bit 7. Files 2 and 3 are the other mode's pair.
"""
import struct

from tools.lib import mp7, mpdata

MP7_ARCHIVE = "files/data/w02.bin"
MP7_SPACES_FILE = 0
SPACES = 88
START = 37                            # type 0x8000
SUMMIT = 54
SUMMIT_EXIT, SUMMIT_EXIT_TO = 74, 27  # the dead end after the summit, and where it now leads
TYPE_START, TYPE_SIDE, TYPE_SHOP, TYPE_MP7_ONLY = 0x8000, 0x2000, 0x20, 0x100
COLOURS = {11: 1}                     # MP7 colour -> MP6 colour


def parse(blob):
    """Space records as dicts: head (the first 36 bytes), type, flags, colour, links (1-based ids)."""
    count = struct.unpack_from(">I", blob, 0)[0]
    pos, spaces = 4, []
    for _ in range(count):
        kind, flags, colour, n = struct.unpack_from(">HIHH", blob, pos + 36)
        links = [link + 1 for link in struct.unpack_from(f">{n}H", blob, pos + 46)]
        spaces.append({"head": bytes(blob[pos:pos + 36]), "type": kind, "flags": flags,
                       "colour": colour, "links": links})
        pos += 46 + 2 * n
    if pos != len(blob):
        raise ValueError(f"space table is {len(blob)} bytes, records end at {pos}")
    return spaces


def build(spaces):
    out = bytearray(struct.pack(">I", len(spaces)))
    for s in spaces:
        out += s["head"] + struct.pack(">HIHH", s["type"], s["flags"], s["colour"], len(s["links"]))
        out += struct.pack(f">{len(s['links'])}H", *(link - 1 for link in s["links"]))
    return bytes(out)


def check_mp7(spaces):
    """Raise unless the table is the Pagoda Peak layout this module was written against."""
    problems = []
    if len(spaces) != SPACES:
        problems.append(f"{len(spaces)} spaces, expected {SPACES}")
    else:
        starts = [i + 1 for i, s in enumerate(spaces) if s["type"] & TYPE_START]
        if starts != [START]:
            problems.append(f"start spaces {starts}, expected [{START}]")
        if spaces[SUMMIT_EXIT - 1]["links"] or SUMMIT_EXIT not in spaces[SUMMIT - 1]["links"]:
            problems.append(f"space {SUMMIT_EXIT} is not the summit's dead end")
    if problems:
        raise RuntimeError("MP7 w02.bin file 0: " + "; ".join(problems))


def convert(spaces):
    """Pagoda Peak's spaces for MP6 (see the docstring): MP7's flags kept, type 0x100 and colour 11 mapped,
    the summit's dead end linked back to the bottom."""
    check_mp7(spaces)
    out = []
    for space_id, s in enumerate(spaces, 1):
        s = dict(s, links=list(s["links"]))
        s["type"] &= ~TYPE_MP7_ONLY
        s["colour"] = COLOURS.get(s["colour"], s["colour"])
        if space_id == SUMMIT_EXIT:
            s["links"] = [SUMMIT_EXIT_TO]
        out.append(s)
    return out


def check_converted(spaces):
    """What the engine needs: one start, and every walkable space reachable from the start with a way on."""
    by_id = dict(enumerate(spaces, 1))
    starts = [i for i, s in by_id.items() if s["type"] & TYPE_START]
    assert starts == [START], starts

    def walkable(i):
        return not by_id[i]["type"] & (TYPE_SIDE | TYPE_SHOP)
    seen, todo = set(), [START]
    while todo:
        i = todo.pop()
        if i in seen:
            continue
        seen.add(i)
        onward = [link for link in by_id[i]["links"] if walkable(link)]
        assert onward, f"space {i} is a dead end"
        todo += onward


def mp7_file(archive, number):
    """File `number` of the MP7 archive `archive` ("files/data/w02.bin"), decompressed."""
    data = mp7.read(archive)
    count = struct.unpack_from(">I", data, 0)[0]
    return mpdata.read_file(data, list(struct.unpack_from(f">{count}I", data, 4)), number)


def mp7_spaces():
    """The converted table, from the user's MP7 disc."""
    spaces = convert(parse(mp7_file(MP7_ARCHIVE, MP7_SPACES_FILE)))
    check_converted(spaces)
    return build(spaces)


def mp7_layer1(number):
    """MP7 w02.bin `number` (masu layer 1: each space's link to the ledge below), checked and unchanged."""
    table = mp7_file(MP7_ARCHIVE, number)
    if len(parse(table)) != SPACES:     # parse raises on a malformed table
        raise RuntimeError(f"MP7 w02.bin file {number}: expected {SPACES} spaces")
    return table
