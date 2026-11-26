"""Where the PAL game hard-codes its set of boards: tables and code sites in main.dol and the RELs.

Each Table says where the table is, the struct format of one entry, how it ends (a fixed count or
a terminator in the first field), what indexes it and what a new board needs from it. Each Site is
one instruction that encodes a board limit, with its vanilla word. read_table() and read_site()
decode them from a DOL or REL blob; tools.scripts.board_tables_dump prints them all.

A new party board would be board number 11: 0-10 are all taken (GW_BOARD_NO in
include/game/gamework_enum.h). docs/board-tables.md explains each entry and the plan for it.
"""
import struct
from dataclasses import dataclass

from tools.lib.dol import dol_offset

NEW_BOARD_NO = 11
MAX_ROWS = 4096         # a table without its terminator within this many rows is an error


@dataclass(frozen=True)
class Table:
    name: str
    file: str            # "main.dol" or a REL in files/dll
    where: int           # DOL address, or offset in REL section `section`
    fmt: str             # struct format of one entry, big-endian
    count: int | None    # fixed entry count, or None when the table ends at `end`
    end: int | None      # first-field value of the terminator entry
    expected: int        # vanilla entry count (terminator not counted)
    index: str           # what the game indexes it by
    board11: str         # what a new board needs from it
    section: int = 0     # REL section (0 for the DOL)


@dataclass(frozen=True)
class Site:
    name: str
    file: str
    where: int           # DOL address, or offset in REL section `section`
    word: int            # vanilla instruction
    board11: str
    section: int = 0


TABLES = (
    # --- main.dol: lists the game walks to a terminator -------------------------------------
    Table("overlays", "main.dol", 0x8022D404, ">Ii", None, 0, 131,
          "overlay number (DLL_*); omOvlCall", "a w07dll.rel entry: move the table (one reference, "
          "0x80005A10) or reuse a stub slot (0x70 partyresultdll, 0x79 storyresultdll)"),
    Table("data_dirs", "main.dol", 0x8021BEF0, ">Ii", None, 0, 261,
          "data dir number (dir << 16 | file)", "w07/w07n entries appended at 261, 262 (inserting "
          "renumbers waluigi...yoshimot); or keep using w01/w01n"),
    Table("sound_groups", "main.dol", 0x8022B810, ">hhh2xiibb2x", None, -1, 121,
          "overlay number, linear search", "a row for the new overlay (else MG601's group)"),
    Table("step_sounds", "main.dol", 0x8022ED58, ">hh", None, -1, 112,
          "overlay number, linear search", "optional: footstep type, has a default"),
    # --- main.dol: indexed by boardNo (GwSystem+8 & 0x1F) -------------------------------------
    Table("board_music", "main.dol", 0x802651F8, ">iiii", None, -1, 11,
          "boardNo, searched (mbMusBoardPlay fn_8016DC3C)", "a {11, day, night, flag} row: move the table"),
    Table("orb_lists", "main.dol", 0x80267D20, ">iI", None, -1, 11,
          "boardNo, searched (mbCapListRead fn_801C7EDC)", "a {11, capsule file} row: without it "
          "file -1 is loaded"),
    Table("camera", "main.dol", 0x8021A2E0, ">i5f", 11, None, 11,
          "boardNo, searched (mbCameraInit fn_8014EC94)", "nothing: falls back to entry 0, all equal"),
    Table("cap_throw", "main.dol", 0x802679B4, ">I", 11, None, 11,
          "boardNo clamped to 0..10 (fn_801C2690)", "nothing"),
    Table("pause_logos", "main.dol", 0x8021A828, ">I", 11, None, 11,
          "boardNo, unchecked (PauseMain fn_8019190C)", "entry 11: move the table or redirect"),
    Table("telops", "main.dol", 0x8021AAF0, ">I", 27, None, 27,
          "board names at boardNo + 16, unchecked (ev_OpeningParty fn_8018EB9C)", "entry 27"),
    Table("welcome_messages", "main.dol", 0x80265D20, ">I", 6, None, 6,
          "boardNo, unchecked (ev_OpeningParty fn_8018EB9C)", "entry 11 (only 0-5 exist)"),
    # --- RELs ------------------------------------------------------------------------------
    Table("party_board_dlls", "mdpartydll.rel", 0x7C, ">I", 6, None, 6,
          "board select cursor (copied to the stack in fn_1_129C, fn_1_2DF8C)",
          "a 7th overlay number; the 3D board select also lays out 6 boards", section=4),
    Table("result_counts", "mdpresultdll.rel", 0x3A8, ">h", 6, None, 6,
          "boardNo (party results)", "entry 11", section=5),
    Table("result_sprites", "mdpresultdll.rel", 0x3B4, ">24I", 6, None, 6,
          "boardNo, 0x60 bytes each (party results)", "entry 11", section=5),
)

SITES = (
    Site("charman_win_voice_lo", "main.dol", 0x80059000, 0x2C03007B,
         "board overlays w01..w11 skip the win voice (cmpwi r3,0x7B / 0x82); a new overlay outside "
         "the range plays it"),
    Site("charman_win_voice_hi", "main.dol", 0x8005900C, 0x2C030082, "see charman_win_voice_lo"),
    Site("charman_board_win", "main.dol", 0x80061784, 0x2C00007B, "w01 only: win animation length"),
    *(Site(f"w0{n + 1}_board_no", f"w0{n + 1}Dll.rel", 0xCC, 0x38600000 | n,
           "li r3,boardNo before mbObjectSetup: a clone changes it to li r3,11", section=1)
      for n in range(6)),
)


@dataclass(frozen=True)
class Read:
    """A board-number read: `lbz r0,8(rX)` (GwSystem+8), then `clrlwi rd,rs,27` at `where`."""
    name: str
    file: str
    where: int           # DOL address, or .text offset in a REL
    rd: int
    rs: int


# The reads a board alias hooks (apply_clone_board_patch.py). Not listed, and why: the camera falls
# back to entry 0 and the orb throw clamps; mbObjectSetup, fn_8014BE04 and the mdpartydll rlwimi
# sites write the number; resultDll bounds-checks; the board RELs never use their copy; the rest
# is solo-mode code.
BOARD_NO_READS = (
    Read("music_play", "main.dol", 0x8016DC74, 29, 0),        # mbMusBoardPlay
    Read("music_fade", "main.dol", 0x8016F048, 26, 0),        # MusBoardFade
    Read("orb_list", "main.dol", 0x801C7F0C, 26, 0),          # mbCapListRead
    Read("pause_logo", "main.dol", 0x80191950, 26, 0),        # PauseMain
    Read("opening_telop", "main.dol", 0x8018ED58, 20, 0),     # ev_OpeningParty
    Read("opening_welcome", "main.dol", 0x8018EE90, 19, 0),   # ev_OpeningParty
    Read("cap_donkey", "main.dol", 0x801BC668, 0, 0),         # ev_CapDonkeyStart (boardNo == 3)
    Read("cap_koopa", "main.dol", 0x801BEB94, 17, 0),         # ev_CapKoopaStart (boardNo == 3)
    Read("cap_col_mdl", "main.dol", 0x801D389C, 31, 0),       # CapColMdlIdGet
    Read("party_5a0", "mdpartydll.rel", 0x7F0, 0, 0),
    Read("party_launch_a", "mdpartydll.rel", 0x13B0, 0, 0),   # fn_1_129C: board DLL table
    Read("party_launch_b", "mdpartydll.rel", 0x13D8, 0, 0),
    Read("party_2df8c_a", "mdpartydll.rel", 0x2E32C, 0, 0),   # board DLL table
    Read("party_2df8c_b", "mdpartydll.rel", 0x2E354, 0, 0),
    Read("party_cursor", "mdpartydll.rel", 0x30648, 3, 7),    # fn_1_305E0: cursor = boardNo
    Read("party_reset", "mdpartydll.rel", 0x1014, 3, 0),      # fn_1_918: fn_8014BE04(boardNo)
    Read("results", "mdpresultdll.rel", 0x594, 4, 0),         # fn_1_56C: results and records
)


def clrlwi27(rd, rs):
    """clrlwi rd, rs, 27 (rlwinm rd, rs, 0, 27, 31): the board number's 5 bits."""
    return (21 << 26) | (rs << 21) | (rd << 16) | (27 << 6) | (31 << 1)


def rel_section(rel, section):
    """File offset of a REL section."""
    count, table = struct.unpack_from(">II", rel, 0x0C)
    offset = struct.unpack_from(">I", rel, table + 8 * section)[0] & ~1 if section < count else 0
    if not offset:
        raise ValueError(f"REL section {section} has no data in the file")
    return offset


def _offset(blob, where, section):
    return rel_section(blob, section) + where if section else dol_offset(blob, where)


def read_table(blob, table):
    """Entries of `table` as tuples, without the terminator."""
    size = struct.calcsize(table.fmt)
    start = _offset(blob, table.where, table.section)
    rows = []
    for index in range(table.count if table.count is not None else MAX_ROWS + 1):
        position = start + index * size
        if position + size > len(blob):
            raise ValueError(f"{table.name}: runs past the end of {table.file}")
        row = struct.unpack_from(table.fmt, blob, position)
        if table.count is None and row[0] == table.end:
            return rows
        rows.append(row)
    if table.count is None:
        raise ValueError(f"{table.name}: no terminator {table.end} within {MAX_ROWS} entries")
    return rows


def read_site(blob, site):
    return struct.unpack_from(">I", blob, _offset(blob, site.where, site.section))[0]


def read_word(blob, file, where):
    """The instruction at a DOL address (file "main.dol") or a REL .text offset."""
    return struct.unpack_from(">I", blob, _offset(blob, where, 0 if file == "main.dol" else 1))[0]


def dol_string(dol, address):
    """A NUL-terminated string at a DOL address."""
    start = dol_offset(dol, address)
    return dol[start:dol.index(b"\0", start)].decode("latin-1")
