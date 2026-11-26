"""Clone board: board number 11 runs from a new dll/w07dll.rel as a copy of Snowflake Lake (w04, board 3).

This proves a 7th party board slot before any new content goes in (docs/board-tables.md). Board 11
borrows board 3's entry in every table indexed by board number, so no table moves:
  * Every board-number read in tools.lib.board_tables.BOARD_NO_READS is `lbz r0,8(GwSystem)` then
    `clrlwi rd,rs,27`. The clrlwi becomes `bl` to a stub in the new section:
        clrlwi rd,rs,27; cmplwi cr7,rd,11; bnelr cr7; li rd,3; blr
    one stub per (rd, rs) pair. None of the hooked functions use cr7, and all save LR.
    Hooked: board music, orb list, pause logo, the opening name card and welcome text, the two
    boardNo == 3 capsule events, CapColMdlIdGet (DOL); mdpartydll's reads (the board DLL table and the
    cursor reset after a game); mdpresultdll fn_1_56C, so the 6-entry result tables and the record
    writers see 3 and the save arrays stay in range (board 11's records count under Snowflake Lake).
  * Overlay slot 0x70 (partyresultdll, a 156-byte stub nothing loads) is re-pointed to "dll/w07dll.rel".
  * HuAudDllSndGrpSet: `mr r28,r3` (0x800413D4) becomes `bl` to a stub that maps overlay 0x70 to 0x7E
    (w04dll), so the clone gets w04's sound group.
  * w07dll.rel = w04Dll.rel (current output, else the original) with .text+0xCC `li r3,3` -> `li r3,11`,
    the board number passed to mbObjectSetup. It keeps w04's data dirs (233/234) and message bank.
  * Left alone: the charman win voice range 0x7B-0x82 excludes 0x70, so the win voice plays on the board.

The board select reaches overlay 0x70 through page 2 (apply_party_pages_patch.py EXTRA_BOARDS). Until
2026-11-25 the test aid clone_board_menu pointed Snowflake Lake's icon at it instead.

Code: DOL section 18 in free text slot 2 (all data slots are used) at 0x802F9DA0, right after
section 17 (apply_egadd_morpher_patch.py); the OSSetArenaLo clamp is raised to its end.
Outputs: build/GP6P01/main.dol; files/dll/w07dll.rel, mdpartydll.rel (from party_pages's
build/GP6P01/mdpartydll/mdpartydll.rel, else the original; installing it is this step's) and mdpresultdll.rel
(from random_bonus's build/GP6P01/mdpresultdll/mdpresultdll.rel).
Run after unlucky (needs section 17). Idempotent.
Status: confirmed in Dolphin (2026-11-24) with clone_board_menu: the log shows DLLStart 112 and sound
group 25; opening, music, orb shop, pause, a full game, results, return to board select and saving all work,
and the other boards' records are unchanged.
"""
import struct

from tools.lib.board_tables import BOARD_NO_READS, NEW_BOARD_NO, clrlwi27, dol_string
from tools.lib.dol import dol_offset, encode_branch, replace_bytes
from tools.lib.paths import BUILD, DOL, REL_DIR, REL_ORIG
from tools.lib.ppc import BLR, i_li, i_rlwinm
from tools.lib.rel import add_calls, check_words, import_blocks, text_base, walk_relocs
from tools.patches import apply_egadd_morpher_patch as morpher
from tools.patches import apply_mgtable_move_patch as mg

ALIAS = 3                       # Snowflake Lake
OVERLAY_SLOT = 0x70             # partyresultdll
ALIAS_OVERLAY = 0x7E            # w04dll
OVERLAY_TABLE = 0x8022D404      # {char *path, 0} x 131
ORIGINAL_PATH = "dll/partyresultdll.rel"
REL_SOURCE = "w04Dll.rel"
REL_NAME = "w07dll.rel"
PATH = f"dll/{REL_NAME}".encode()
BOARD_NO_SITE = 0xCC            # .text: li r3,boardNo before bl mbObjectSetup
MDPRESULT_BUILT = BUILD / "mdpresultdll" / "mdpresultdll.rel"
MDPARTY_BUILT = BUILD / "mdpartydll" / "mdpartydll.rel"     # apply_party_pages_patch.py's rebuild

SOUND_SITE = 0x800413D4         # HuAudDllSndGrpSet: mr r28, r3
SOUND_WORD = 0x7C7C1B78

SECTION = 2                     # text slot
CODE_BASE = morpher.CODE_END    # 0x802F9DA0
CODE_SIZE = 0x400
CODE_END = CODE_BASE + CODE_SIZE
PATH_ADDR = CODE_BASE           # 0x20 bytes
SOUND_STUB = CODE_BASE + 0x20   # 6 words
STUBS = CODE_BASE + 0x40        # 5 words each
STUB_SIZE = 0x14

BNELR_CR7 = 0x4C9E0020


def cmplwi_cr7(ra, imm):
    return (10 << 26) | (7 << 23) | (ra << 16) | imm


def stub_pairs():
    return sorted({(r.rd, r.rs) for r in BOARD_NO_READS})


def stub_address(rd, rs):
    return STUBS + STUB_SIZE * stub_pairs().index((rd, rs))


def alias_stub(rd, rs):
    return [clrlwi27(rd, rs), cmplwi_cr7(rd, NEW_BOARD_NO), BNELR_CR7, i_li(rd, ALIAS), BLR]


def sound_stub():
    return [SOUND_WORD, i_rlwinm(0, 3, 0, 16, 31), cmplwi_cr7(0, OVERLAY_SLOT), BNELR_CR7,
            i_li(28, ALIAS_OVERLAY), BLR]


def section_code():
    """The used part of the section: path string, sound stub, one alias stub per register pair."""
    code = bytearray(PATH.ljust(SOUND_STUB - PATH_ADDR, b"\0"))
    code += struct.pack(">6I", *sound_stub()).ljust(STUBS - SOUND_STUB, b"\0")
    for rd, rs in stub_pairs():
        code += struct.pack(">5I", *alias_stub(rd, rs))
    assert len(code) <= CODE_SIZE
    return bytes(code)


def add_section(dol):
    """Text section SECTION at CODE_BASE (zero-filled); the arena clamp moves up to CODE_END."""
    if struct.unpack_from(">I", dol, 0x48 + 4 * morpher.SECTION)[0] != morpher.CODE_BASE:
        raise SystemExit("DOL section 17 is missing: run apply_egadd_morpher_patch.py first")
    positions = (4 * SECTION, 0x48 + 4 * SECTION, 0x90 + 4 * SECTION)
    current = tuple(struct.unpack_from(">I", dol, p)[0] for p in positions)
    if current[1:] != (CODE_BASE, CODE_SIZE):
        if any(current):
            raise RuntimeError(f"DOL section slot {SECTION} is already in use: {[hex(v) for v in current]}")
        while len(dol) % 0x20:
            dol.append(0)
        for position, value in zip(positions, (len(dol), CODE_BASE, CODE_SIZE)):
            struct.pack_into(">I", dol, position, value)
        dol.extend(b"\0" * CODE_SIZE)
        print(f"Added DOL section {SECTION} (text slot): {CODE_BASE:#010x}-{CODE_END:#010x}")
    at = dol_offset(dol, mg.ARENA_CAVE)
    hi, low = struct.unpack_from(">2I", dol, at)
    if hi >> 16 != 0x3C00 or low >> 16 != 0x6000:
        raise RuntimeError("OSSetArenaLo clamp not found: run apply_mgtable_move_patch.py first")
    if ((hi & 0xFFFF) << 16 | (low & 0xFFFF)) < CODE_END:
        struct.pack_into(">2I", dol, at, 0x3C000000 | (CODE_END >> 16), 0x60000000 | (CODE_END & 0xFFFF))
        print(f"OSSetArenaLo now clamps ArenaLo to >= {CODE_END:#010x}")


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    add_section(dol)

    code = section_code()
    start = dol_offset(dol, CODE_BASE)
    if bytes(dol[start:start + len(code)]) not in (b"\0" * len(code), code):
        raise RuntimeError(f"Section {SECTION} at {CODE_BASE:#010x} holds unexpected bytes")
    dol[start:start + len(code)] = code

    for read in (r for r in BOARD_NO_READS if r.file == "main.dol"):
        bl = encode_branch(read.where, stub_address(read.rd, read.rs), link=True)
        patch_word(dol, read.where, clrlwi27(read.rd, read.rs), bl, read.name)
    patch_word(dol, SOUND_SITE, SOUND_WORD, encode_branch(SOUND_SITE, SOUND_STUB, link=True), "sound group")

    entry = OVERLAY_TABLE + 8 * OVERLAY_SLOT
    pointer = struct.unpack_from(">I", dol, dol_offset(dol, entry))[0]
    if pointer != PATH_ADDR:
        if dol_string(dol, pointer) != ORIGINAL_PATH:
            raise RuntimeError(f"Overlay {OVERLAY_SLOT:#x} is {dol_string(dol, pointer)!r}, not {ORIGINAL_PATH!r}")
        struct.pack_into(">I", dol, dol_offset(dol, entry), PATH_ADDR)
    DOL.write_bytes(dol)
    print(f"main.dol: board {NEW_BOARD_NO} aliases board {ALIAS}; overlay {OVERLAY_SLOT:#x} -> {PATH.decode()}")


def patch_word(dol, address, original, patched, name):
    replace_bytes(dol, dol_offset(dol, address), struct.pack(">I", original), struct.pack(">I", patched), name)


def write_clone_rel():
    source = REL_DIR / REL_SOURCE if (REL_DIR / REL_SOURCE).exists() else REL_ORIG / REL_SOURCE
    rel = bytearray(source.read_bytes())
    for block in import_blocks(rel).values():
        if any(section == 1 and cursor == BOARD_NO_SITE for _, section, cursor, *_ in walk_relocs(rel, block)):
            raise RuntimeError(f"{REL_SOURCE} has a relocation at .text {BOARD_NO_SITE:#x}")
    check_words(rel, BOARD_NO_SITE, f"{0x38600000 | ALIAS:08X}")
    struct.pack_into(">I", rel, text_base(rel) + BOARD_NO_SITE, 0x38600000 | NEW_BOARD_NO)
    REL_DIR.mkdir(parents=True, exist_ok=True)
    (REL_DIR / REL_NAME).write_bytes(rel)
    print(f"{REL_NAME}: {source.name} with li r3,{NEW_BOARD_NO}")


def hook_rel(name, source):
    rel = bytearray(source.read_bytes())
    sites = []
    for read in (r for r in BOARD_NO_READS if r.file == name):
        check_words(rel, read.where, f"{clrlwi27(read.rd, read.rs):08X}", "48000001")
        sites.append((read.where, stub_address(read.rd, read.rs)))
    added = add_calls(rel, sites)
    REL_DIR.mkdir(parents=True, exist_ok=True)
    (REL_DIR / name).write_bytes(rel)
    print(f"{name}: {len(sites)} board-number reads hooked ({added} new) from {source}")


def main():
    patch_dol()
    write_clone_rel()
    hook_rel("mdpartydll.rel", MDPARTY_BUILT if MDPARTY_BUILT.exists() else REL_ORIG / "mdpartydll.rel")
    hook_rel("mdpresultdll.rel", MDPRESULT_BUILT if MDPRESULT_BUILT.exists() else REL_ORIG / "mdpresultdll.rel")


if __name__ == "__main__":
    main()
