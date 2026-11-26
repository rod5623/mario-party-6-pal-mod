"""Board 11 (the clone board) gets Pagoda Peak's presentation from Mario Party 7: music, logo, welcome text.

The board itself is still the Snowflake Lake copy from apply_clone_board_patch.py. Content comes
from the user's MP7 PAL disc (tools.lib.mp7: src/orig/GP7P01/ if extracted, else GP7P01.iso):
  * Music: MP7_Str.pdt track 12 (MP7's board music table at 0x80294CC0 maps board 1, Pagoda Peak, to
    12; the PDT format is the same). Appended to MP6_Str.pdt as track 111, after Close Call's 110.
  * Logo: file 0x4E of each MP7 board*.bin (its pause logo table, entries 12-22 of 0x80249B88), C8
    256x240. Appended as file 189 of the matching MP6 board*.bin, after the Castaway wheel icons.
    MP6 shows the same sprite as the pause logo and as the opening name card.
  * Welcome text: MP7 bank 0x11 record 1 ("Welcome to Pagoda Peak! ..."), each language from the
    matching MP7 file, behind that MP6 file's own welcome record header. Appended to bank 0x2C as
    record 19 (message 0x2C0013).

So board 11 has its own entries where these live, instead of aliasing board 3:
  * The clone board's alias hooks on music play/fade, pause logo, name card and welcome text
    (OWN_READS) go back to the original clrlwi. The other reads keep aliasing 11 to 3.
  * Four tables move into section 18 (after clone_board's stubs) with a board-11 entry, and every
    lis/addi pair that addresses them is re-pointed (REFERENCES):
      board music  0x802651F8 -> 11 rows + {11, 111, 111, 1} + terminator   (14 references)
      pause logos  0x8021A828 -> 12 entries, [11] = 0x50000 | 189           (2)
      name cards   0x8021AAF0 -> 28 entries, [27] = 0x50000 | 189           (3)
      welcome text 0x80265D20 -> 12 entries, [6..10] = [0], [11] = 0x2C0013 (1)

Outputs: build/GP6P01/main.dol, files/sound/MP6_Str.pdt, files/data/board*.bin, files/mess/messdata*.bin
(each read from the current output, else the original). Run after clone_board, closecall and
castaway_wheel. Idempotent.
Status: confirmed in Dolphin (2026-11-24) with clone_board_menu: the opening name card, welcome text
(MP7's 0x85 ends it with a full stop in MP6's font), board music and pause logo are Pagoda Peak's. The
256x240 logo shows fine. A full game to results with this step on is not yet checked.
"""
import struct

from tools.audio import pdt
from tools.lib import messages, mp7, mpdata
from tools.lib.board_tables import BOARD_NO_READS, NEW_BOARD_NO, clrlwi27
from tools.lib.dol import dol_offset, encode_branch, replace_bytes
from tools.lib.paths import BUILD, DATA_ORIG, DATA_OUT, DOL, MESS_NAMES, MESS_OUTPUT_DIR, MESS_SOURCE_DIR
from tools.lib.ppc import ha, lo
from tools.patches import apply_clone_board_patch as clone

MP7_TRACK = 12
TRACK = 111                     # after the 110 retail tracks and Close Call's 110
PDT_OUT = BUILD / "files" / "sound" / "MP6_Str.pdt"

MP7_LOGO = 0x4E
LOGO_FILE = 189                 # after the Castaway wheel icons (185-188)
LOGO = 0x50000 | LOGO_FILE      # data number in board*.bin (dir 5)
BOARD_ARCHIVES = ("board", "board_fr", "board_ge", "board_it", "board_sp", "board_us")

MP7_BANK, MP7_RECORD = 0x11, 1
BANK = 0x2C                     # MP6 BOARD_OPENING: records 0-5 are the boards' welcome lines
BANK_RECORDS = 19
WELCOME = (BANK << 16) | BANK_RECORDS
HEADER_FROM = 3                 # copy the record header of MP6's Snowflake Lake welcome line

OWN_READS = ("music_play", "music_fade", "pause_logo", "opening_telop", "opening_welcome")

MUSIC_TABLE, MUSIC_ROWS = 0x802651F8, 11
PAUSE_TABLE, PAUSE_COUNT = 0x8021A828, 11
TELOP_TABLE, TELOP_COUNT = 0x8021AAF0, 27
WELCOME_TABLE, WELCOME_COUNT = 0x80265D20, 6

TABLES_BASE = 0x802F9EC0        # section 18, after clone_board's code (ends 0x802F9EA8)
NEW_MUSIC = TABLES_BASE                          # 13 x 16 bytes
NEW_PAUSE = NEW_MUSIC + 16 * (MUSIC_ROWS + 2)    # 12 words
NEW_TELOP = NEW_PAUSE + 4 * (NEW_BOARD_NO + 1)   # 28 words
NEW_WELCOME = NEW_TELOP + 4 * (TELOP_COUNT + 1)  # 12 words
TABLES_END = NEW_WELCOME + 4 * (NEW_BOARD_NO + 1)

# (lis address, addi address): every reference to the four tables (all adjacent lis/addi pairs)
REFERENCES = {
    MUSIC_TABLE: (NEW_MUSIC, [0x8016DC54, 0x8016DC7C, 0x8016DC98, 0x8016DCD0, 0x8016DCE8, 0x8016DD00, 0x8016DD1C,
                              0x8016F028, 0x8016F050, 0x8016F06C, 0x8016F0A4, 0x8016F0BC, 0x8016F0D4, 0x8016F0F0]),
    PAUSE_TABLE: (NEW_PAUSE, [0x80191958, 0x80191F70]),
    TELOP_TABLE: (NEW_TELOP, [0x8020326C, 0x802033E0, 0x802034F4]),
    WELCOME_TABLE: (NEW_WELCOME, [0x8018EE9C]),
}


def words(dol, address, count, fmt=">I"):
    start = dol_offset(dol, address)
    return list(struct.unpack_from(f">{count}{fmt[1:]}", dol, start))


def new_tables(dol):
    """The four moved tables, built from the vanilla ones in `dol`, as one blob at TABLES_BASE."""
    music = [words(dol, MUSIC_TABLE + 16 * i, 4, ">i") for i in range(MUSIC_ROWS + 1)]
    if [row[0] for row in music] != list(range(MUSIC_ROWS)) + [-1]:
        raise RuntimeError(f"Unexpected board music table: {music}")
    music = music[:-1] + [[NEW_BOARD_NO, TRACK, TRACK, 1], [-1, 0, 0, 0]]
    pause = words(dol, PAUSE_TABLE, PAUSE_COUNT) + [LOGO]
    telop = words(dol, TELOP_TABLE, TELOP_COUNT) + [LOGO]
    welcome = words(dol, WELCOME_TABLE, WELCOME_COUNT)
    welcome = welcome + [welcome[0]] * (NEW_BOARD_NO - WELCOME_COUNT) + [WELCOME]
    blob = b"".join(struct.pack(">4i", *row) for row in music)
    for table in (pause, telop, welcome):
        blob += struct.pack(f">{len(table)}I", *table)
    assert len(blob) == TABLES_END - TABLES_BASE
    return blob


def repoint(dol, lis_address, old, new):
    """Point the lis/addi pair at lis_address from table `old` to `new` (accepts either)."""
    for address, old_imm, new_imm in ((lis_address, ha(old), ha(new)), (lis_address + 4, lo(old), lo(new))):
        word = struct.unpack_from(">I", dol, dol_offset(dol, address))[0]
        original = (word & 0xFFFF0000) | old_imm
        patched = (word & 0xFFFF0000) | new_imm
        replace_bytes(dol, dol_offset(dol, address), struct.pack(">I", original), struct.pack(">I", patched),
                      f"reference at {address:#010x}")


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    if struct.unpack_from(">I", dol, 0x48 + 4 * clone.SECTION)[0] != clone.CODE_BASE:
        raise SystemExit("DOL section 18 is missing: run apply_clone_board_patch.py first")
    if TABLES_END > clone.CODE_END or TABLES_BASE < clone.CODE_BASE + len(clone.section_code()):
        raise RuntimeError("The moved tables don't fit in section 18 after the clone board's code")

    # Built from the vanilla tables, which stay where they were (only the references move).
    blob = new_tables(dol)
    start = dol_offset(dol, TABLES_BASE)
    if bytes(dol[start:start + len(blob)]) not in (b"\0" * len(blob), blob):
        raise RuntimeError(f"Section 18 at {TABLES_BASE:#010x} holds unexpected bytes")
    dol[start:start + len(blob)] = blob

    for old, (new, sites) in REFERENCES.items():
        for site in sites:
            repoint(dol, site, old, new)

    for read in (r for r in BOARD_NO_READS if r.name in OWN_READS):
        bl = encode_branch(read.where, clone.stub_address(read.rd, read.rs), link=True)
        replace_bytes(dol, dol_offset(dol, read.where), struct.pack(">I", bl),
                      struct.pack(">I", clrlwi27(read.rd, read.rs)), f"{read.name} (clone board hook)")
    DOL.write_bytes(dol)
    print(f"main.dol: board {NEW_BOARD_NO} has its own music, logo and welcome entries "
          f"({TABLES_BASE:#010x}-{TABLES_END:#010x})")


def patch_music():
    source = pdt.read_track(mp7.read("files/sound/MP7_Str.pdt"), MP7_TRACK)
    if not PDT_OUT.exists():
        raise SystemExit(f"{PDT_OUT} is missing: run apply_closecall_patch.py first")
    current = PDT_OUT.read_bytes()
    count = struct.unpack_from(">H", current, 2)[0]
    if count == TRACK + 1:
        existing = pdt.read_track(current, TRACK)
        if (existing.left, existing.right, existing.nibbles) != (source.left, source.right, source.nibbles):
            raise RuntimeError(f"{PDT_OUT}: track {TRACK} is not MP7 track {MP7_TRACK}")
        print(f"sound/MP6_Str.pdt: track {TRACK} already holds MP7 track {MP7_TRACK}")
        return
    if count != TRACK:
        raise SystemExit(f"{PDT_OUT}: {count} tracks, expected {TRACK} (run apply_closecall_patch.py first)")
    first = pdt.append_tracks(PDT_OUT, PDT_OUT, [source])
    print(f"sound/MP6_Str.pdt: track {first} = MP7 track {MP7_TRACK} "
          f"({source.nibbles * 7 / 8 / source.rate:.0f} s, loops)")


def drop_last_file(data, offsets):
    count = len(offsets) - 1
    body = data[4 + 4 * len(offsets):offsets[-1]]
    new_offsets = [o - 4 for o in offsets[:-1]]
    return struct.pack(f">I{count}I", count, *new_offsets) + body, new_offsets


def patch_logos():
    for name in BOARD_ARCHIVES:
        out = DATA_OUT / f"{name}.bin"
        source = out if out.exists() else DATA_ORIG / f"{name}.bin"
        data, offsets = mpdata.read_archive(source)
        while len(offsets) > LOGO_FILE:  # drop an earlier build of the logo
            data, offsets = drop_last_file(data, offsets)
        if len(offsets) != LOGO_FILE:
            raise SystemExit(f"{source}: {len(offsets)} files, expected {LOGO_FILE} "
                             "(run apply_castaway_wheel_patch.py first)")
        mp7_data = mp7.read(f"files/data/{name}.bin")
        mp7_archive = (mp7_data, list(struct.unpack_from(f">{struct.unpack_from('>I', mp7_data)[0]}I", mp7_data, 4)))
        logo = mpdata.read_file(*mp7_archive, MP7_LOGO)
        patched, _ = mpdata.append_files(data, offsets, [logo])
        DATA_OUT.mkdir(parents=True, exist_ok=True)
        out.write_bytes(patched)
    print(f"data/board*.bin: Pagoda Peak logo (MP7 file {MP7_LOGO:#x}) as file {LOGO_FILE} of {len(BOARD_ARCHIVES)} archives")


def bank_record(data, bank, index):
    _, start, end = messages._bounds(data, bank)
    count = struct.unpack_from(">I", data, start)[0]
    offsets = struct.unpack_from(f">{count}I", data, start + 4)
    stop = start + 4 + offsets[index + 1] if index + 1 < count else end
    return bytes(data[start + 4 + offsets[index]:stop])


def patch_welcome():
    for name in MESS_NAMES:
        out = MESS_OUTPUT_DIR / name
        data = out.read_bytes() if out.exists() else (MESS_SOURCE_DIR / name).read_bytes()
        header = bank_record((MESS_SOURCE_DIR / name).read_bytes(), BANK, HEADER_FROM)[:4]
        body = bank_record(mp7.read(f"files/mess/{name}"), MP7_BANK, MP7_RECORD)[4:]
        record = header + body + b"\0" * (-(len(header) + len(body)) % 4)
        patched = messages.append_records(data, {BANK: (BANK_RECORDS, [record])}, f"pagoda_peak {name}")
        MESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out.write_bytes(patched)
    print(f"mess/messdata*.bin: Pagoda Peak welcome text as message {WELCOME:#x}")


def main():
    patch_dol()
    patch_music()
    patch_logos()
    patch_welcome()


if __name__ == "__main__":
    main()
