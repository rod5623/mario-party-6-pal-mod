"""Experiment: the clone board (board 11) walks Mario Party 7's Pagoda Peak spaces, with Snowflake Lake's rules.

MP7 data/w02.bin file 0 is Pagoda Peak's space table, in the same 46-byte record format as MP6 (88 spaces,
LZ type 1). w04Dll loads its table with `mr r3, r28` / `bl mbMasuInit` (fn_801748EC) at .text 0x190, the
only call (r28 = 0xE90000 or 0xEA0000, file 0 of w04.bin / w04n.bin). This aid:
  * converts the MP7 table to Snowflake Lake's meanings and appends it to w04.bin and w04n.bin as file 42,
    after mp7_map_test's map model (file 41), in root/data and build/GP6P01/files/data;
  * changes w07dll.rel .text 0x190 to `ori r3, r28, 42`. The real Snowflake Lake never loads file 42.

What the fields mean (research for this aid, 2026-11-24):
  * Type (u16 at +36, masu+0x10) is engine-wide and the same in both games: 0x8000 is the start (one
    colour-0 node per board; MP7 space 37), 0x8 -> 0x4 pairs are climbs, 0x20 is the shop model's node and
    0x2000 a side node (stands for board objects, event points). fn_801EF3D0 sets the default "never a stop" type mask
    to 0xA020. MP7 adds 0x100 (only on the summit, space 54), which no MP6 code tests: cleared.
  * Flags (u32 at +38, masu+0x14) are board-defined. Snowflake Lake's REL finds every space by flag,
    never by id. Snowflake Lake has no Star Space: its Chain Chomp stations are the 3-bit index in 0x380
    (0x80 = station 1 ... 0x200 = station 4, packed by fn_80177014), each linked to a type 0x2000 node
    where the Chomp's house stands. fn_1_C04 (the move-end hook) offers the Chomp ride there (20 coins by
    day, 10 at night; MP6 message bank 0x32), and fn_1_1D74 builds one station per index, finding
    index i = 1..count with fn_80179238. So indices must be contiguous from 1. Its other bits are gimmicks (0x2, 0x4, 0x8, 0x10/0x20, 0x40 CPU fork
    preference, 0x400, 0x3800, 0x4000, 0x18000). With none set, their hooks never fire and their setup
    counts 0 spaces. All of MP7's flags are dropped. The only one set is 0x80 on the summit (54, stand
    73), so Snowflake Lake's code puts its one Chomp station where Pagoda Peak's Master Koopa sells
    the Star. Pagoda Peak's own Star (MP7 message bank 0x14) is for the C board REL (pagoda_stub).
  * Colour (u16 at +42) codes 0-10 match; MP6's tables (0x80265408 / 0x80265460) don't list 11 in both
    modes, so MP7's colour 11 (spaces 17 and 39) becomes blue. Colours 4 and 6 keep their MP6 meaning
    (Miracle, DK/Bowser).
  * The trail is one line from the start (37) to the summit (54 -> 74, a dead end). MP7's own REL sends
    players back down; here 74 gets a link to 27, the first space after the start, so players walk
    straight from the summit back to the bottom. That's a stopgap until Pagoda Peak has its own code.
  * File 2 is the same graph with 10 colours changed; files 1 and 3 are a bare graph with no colours.
    File 0 is the one used. MP7 w02dll .text 0x124-0x194 picks the pair with GwSystem byte 0 bit 7, the
    same bit that shows the summit's price sign (.text 0x1AD4), which is on in party mode: file 0 with
    file 1 as masu layer 1 (mbMasuDataRead), else file 2 with file 3.
  * mp7_spaces(mp7_flags=True) keeps MP7's flags instead (no Chomp station) for Pagoda Peak's own REL;
    the test aid pagoda_stub writes that table over file 42 while it is on.

    python -m tools.patches.test_aids.apply_mp7_spaces_test_patch        # on
    python -m tools.patches.test_aids.apply_mp7_spaces_test_patch --off  # back to Snowflake Lake's spaces

Run after apply_mp7_map_test_patch.py (re-running that aid or apply_clone_board_patch.py turns this one
off: the archives go back to 42 or 41 files, and clone_board rebuilds the REL). Turn this aid off before
mp7_map_test --off, or the REL would load a missing file 42. The originals are backed up to
backups/w04*.bin.bak_before_mp7_spaces_test before the first edit.

Status: built, not yet tested in Dolphin.
"""
import shutil
import struct
import sys

from tools.lib import mp7, mpdata
from tools.lib.boards import load_spaces
from tools.lib.paths import BACKUPS, DATA_ORIG, DATA_OUT, GAME_DATA, REL_DIR
from tools.lib.rel import check_words, text_base
from tools.patches.apply_pagoda_peak_patch import drop_last_file

MP7_ARCHIVE = "files/data/w02.bin"
ARCHIVES = ("w04", "w04n")
MAP_FILES = 42                        # 41 vanilla files + mp7_map_test's model
NEW_FILE = MAP_FILES                  # file 42
REL_NAME = "w07dll.rel"
SITE = 0x190
ORIGINAL = 0x7F83E378                 # mr r3, r28
PATCHED = 0x63830000 | NEW_FILE       # ori r3, r28, 42

SPACES = 88
START = 37                            # type 0x8000
SUMMIT = 54
STATIONS = {SUMMIT: 1}              # space id -> Chomp station index (the summit's stand is 73)
SUMMIT_EXIT, SUMMIT_EXIT_TO = 74, 27  # the dead end after the summit, and where it now leads
TYPE_START, TYPE_SIDE, TYPE_MP7_ONLY = 0x8000, 0x2000, 0x100
STATION_MASK = 0x380
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


def station_bits(index):
    """Flag bits for Chomp station `index` (1-based) under STATION_MASK (the inverse of fn_80177014)."""
    if not 1 <= index <= STATION_MASK >> 7:
        raise ValueError(index)
    return index << 7


def check_mp7(spaces):
    """Raise unless the table is the Pagoda Peak layout this aid was written against."""
    def at(space_id):
        return spaces[space_id - 1]
    problems = []
    if len(spaces) != SPACES:
        problems.append(f"{len(spaces)} spaces, expected {SPACES}")
    else:
        starts = [i + 1 for i, s in enumerate(spaces) if s["type"] & TYPE_START]
        if starts != [START]:
            problems.append(f"start spaces {starts}, expected [{START}]")
        for spot in STATIONS:
            if not [link for link in at(spot)["links"] if at(link)["type"] & TYPE_SIDE]:
                problems.append(f"Chomp station {spot} has no type {TYPE_SIDE:#x} stand")
        if at(SUMMIT_EXIT)["links"] or SUMMIT_EXIT not in at(SUMMIT)["links"]:
            problems.append(f"space {SUMMIT_EXIT} is not the summit's dead end")
    if problems:
        raise RuntimeError("MP7 w02.bin file 0: " + "; ".join(problems))


def convert(spaces, mp7_flags=False):
    """Pagoda Peak's spaces with Snowflake Lake's meanings (see the docstring); with mp7_flags, MP7's own
    flags are kept for Pagoda Peak's REL."""
    check_mp7(spaces)
    out = []
    for space_id, s in enumerate(spaces, 1):
        s = dict(s, links=list(s["links"]))
        s["type"] &= ~TYPE_MP7_ONLY
        if not mp7_flags:
            s["flags"] = station_bits(STATIONS[space_id]) if space_id in STATIONS else 0
        s["colour"] = COLOURS.get(s["colour"], s["colour"])
        if space_id == SUMMIT_EXIT:
            s["links"] = [SUMMIT_EXIT_TO]
        out.append(s)
    return out


def check_converted(spaces, mp7_flags=False):
    """What the engine needs: one start, and every walkable space reachable from the start with a way on.
    Snowflake Lake's REL also needs station indices 1..n, each with a stand (not checked with mp7_flags)."""
    by_id = dict(enumerate(spaces, 1))
    starts = [i for i, s in by_id.items() if s["type"] & TYPE_START]
    assert starts == [START], starts
    if not mp7_flags:
        check_stations(spaces)
    _check_walkable(by_id)


def check_stations(spaces):
    by_id = dict(enumerate(spaces, 1))
    indices = sorted((s["flags"] & STATION_MASK) >> 7 for s in spaces if s["flags"] & STATION_MASK)
    assert indices == list(range(1, len(indices) + 1)) and indices, indices
    assert all(not s["flags"] & ~STATION_MASK for s in spaces)
    for i, s in by_id.items():
        if s["flags"] & STATION_MASK:
            assert any(by_id[link]["type"] & TYPE_SIDE for link in s["links"]), i


def _check_walkable(by_id):
    def walkable(i):
        return not by_id[i]["type"] & (TYPE_SIDE | 0x20)
    seen, todo = set(), [START]
    while todo:
        i = todo.pop()
        if i in seen:
            continue
        seen.add(i)
        onward = [link for link in by_id[i]["links"] if walkable(link)]
        assert onward, f"space {i} is a dead end"
        todo += onward


def mp7_spaces(mp7_flags=False):
    data = mp7.read(MP7_ARCHIVE)
    count = struct.unpack_from(">I", data, 0)[0]
    blob, _, _ = load_spaces(data, list(struct.unpack_from(f">{count}I", data, 4)))
    spaces = convert(parse(blob), mp7_flags)
    check_converted(spaces, mp7_flags)
    return build(spaces)


def patch_archive(name, table):
    """Write root/data and build/.../data <name>.bin with `table` as file 42 (None: back to 42 files)."""
    game = GAME_DATA / f"{name}.bin"
    source = game if game.exists() else DATA_ORIG / f"{name}.bin"
    backup = BACKUPS / f"{name}.bin.bak_before_mp7_spaces_test"
    if game.exists() and not backup.exists():
        BACKUPS.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(game, backup)
    data, offsets = mpdata.read_archive(source)
    if len(offsets) < MAP_FILES:
        raise SystemExit(f"{source}: {len(offsets)} files, expected at least {MAP_FILES}: "
                         "run apply_mp7_map_test_patch.py first")
    while len(offsets) > MAP_FILES:
        data, offsets = drop_last_file(data, offsets)
    if table is not None:
        data, offsets = mpdata.append_files(data, offsets, [table])
    for out in (game, DATA_OUT / f"{name}.bin"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)


def main():
    off = "--off" in sys.argv[1:]
    path = REL_DIR / REL_NAME
    if not path.exists():
        raise SystemExit(f"{path} is missing: run apply_clone_board_patch.py first")
    rel = bytearray(path.read_bytes())
    check_words(rel, SITE, f"{ORIGINAL:08X}", f"{PATCHED:08X}")
    table = None if off else mp7_spaces()
    for name in ARCHIVES:
        patch_archive(name, table)
    struct.pack_into(">I", rel, text_base(rel) + SITE, ORIGINAL if off else PATCHED)
    path.write_bytes(rel)
    if off:
        print(f"Clone board spaces: Snowflake Lake's again ({', '.join(ARCHIVES)} back to {MAP_FILES} files)")
    else:
        print(f"Clone board spaces: MP7 Pagoda Peak ({SPACES} spaces, Chomp station at {list(STATIONS)}) as file "
              f"{NEW_FILE} of {', '.join(ARCHIVES)}; {REL_NAME} .text {SITE:#x} -> ori r3,r28,{NEW_FILE}")


if __name__ == "__main__":
    main()
