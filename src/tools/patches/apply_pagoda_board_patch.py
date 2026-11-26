"""Board 11 (Pagoda Peak) gets its own archive (data/w07.bin, data dir 261) and message bank (0x4B).

Snowflake Lake's archives and message bank are left vanilla.

The data dir table (0x8021BEF0: 261 entries of {char *path, -1} and a terminator) is fixed in the DOL.
HuDataInit counts it at start-up (DataDirMax), OSPanics if a listed file is missing, and stores each file's
disc entry in the table's second word, so a moved, longer table needs nothing else. Inserting would
renumber waluigi...yoshimot (242-260), so w07 is appended:
  * DOL section 19 in free text slot 3 at 0x802FA1A0, right after section 18 (clone_board, pagoda_peak):
      0x802FA1A0  "data/w07.bin"
      0x802FA1C0  the 261 vanilla entries, {path, -1} for dir 261, the vanilla terminator (to 0x802FA9F8)
    the rest (to 0x802FB1A0) is free. The OSSetArenaLo clamp is raised to the section's end.
  * Every access to it is re-pointed; the vanilla table stays where it was, unused:
      - three lis/addi pairs on the table's own address (HuDataInit and two dir lookups): 0x80007688,
        0x800084A4, 0x80008BC4;
      - seven reads through a base register holding 0x8021AD88 (data.c's string pool) plus 0x1168,
        which the first build missed (the game then panicked at boot, dvd.c:205 File Open Error:
        HuDvdDataFastRead got the old table's unfilled entry). Each is three words, rewritten in place
        with the entry offset already in a register:
          six entry-number reads (BASE_READS)
            addi r3,rB,0x1168; addi r0,r4,4; lwzx r3,r3,r0
         -> addis r3,r4,ha(T+4); addi r0,r4,4; lwz r3,lo(T+4)(r3)
          one path read at 0x80009458 (HuDataReadMulti's path list; r0 is overwritten right after)
            slwi r0,r20,3; addi r3,r24,0x1168; lwzx r3,r3,r0
         -> slwi r3,r20,3; addis r3,r3,ha(T); lwz r3,lo(T)(r3)

One archive for day and night: MP7 has no night Pagoda Peak, and the board REL sets
mbObjDirSet(dir, dir). The engine (fn_80168258 and its copies) only swaps a data number's dir when it
equals the other time's dir, so with both the same the switch changes nothing; MP6's day/night cycle
still runs. Snowflake Lake's shopkeeper is taken from w04.bin (day): its night version differs.

w07.bin, in FILES order (pagoda.h FILE_* must match; tests/test_pagoda_files.py checks):
     0  spaces: MP7 w02.bin 0 with MP7's flags (tools/pagoda/spaces.py)
     1  masu layer 1: MP7 w02.bin 1 (the ledge below each space, for Bowser Time's stomp)
     2  map model: MP7 w02.bin 6
   3-5  Snowflake Lake's shopkeeper, its stand and the smoke on it (vanilla w04.bin 5, 6, 8)
  6-28  MP7 w02.bin: Master Koopa and motions 1-5, house, price sign, gong, rocket, Kung Fu rock, cloud,
        Blazing Rock (burning rock, rock out, flame emitter, fan, chest, T-shirt, flame and smoke sprites),
        dragon, fireball shape and sprite
 29-38  Bowser and his nine motions (MP7 capsulechar1.bin)
 39-41  the bridges, intact, breaking, broken (MP7 w02.bin 0x1D-0x1F)
 42-43  the bamboo pole and the branch (MP7 w02.bin 9, 0xA)
 44-46  the Cannon orb's cannon body, barrel and explosion (MP7 capsule.bin 0x51, 0x50, 0x42)
    47  the view-board area (MP7 w02.bin 4): a hidden mesh whose outer edges bound mbScrollInit's camera
Every file is stored zlib-compressed (mpdata.pack_file).

Orb list: board 11 gets its own row {11, 0x140057} in a copy of the orb list table (0x80267D20) moved
to section 19 (0x802FAA00; its one reference, 0x801C7EF0, re-pointed), and clone_board's 11 -> 3 alias
on mbCapListRead's board read (0x801C7F0C) goes back to the original clrlwi. The list itself is
capsule.bin entry 87 (0x140057, after castaway_wheel's 86): Snowflake Lake's list (entry 0x4D) without
the Snack orb (orb id 0x1E). Star Trap is still appended at run time (star_trap_orb's hook).

Cannon orb (MP7 orb 5; plans/pagoda-peak/README.md 2c-bis, stage 1): orb id 8 (EMPTY in vanilla) becomes a
self orb. Its orb data row (0x80266BDC row 8) gets the model capsule.bin entry 88 (MP7 capsule.bin file 5), the
self frame 0x14001C, the name and description (MP7 bank 0x1B records 71 and 5, as bank 0x4B records 57 and 58),
price 10 and grade 'C'. Its event row (0x80268500 row 8) becomes {exec stub, kill stub, 0, 2, 0, -1, 0}: the
stubs (section 19, 0x802FAAC0 / 0x802FAAE0) jump through two hook words (0x802FAAA0 / 0x802FAAA4) that the board
REL sets at init and clears at kill (cannon.c); with no hook the exec stub ends the orb's process. Pagoda
Peak's list gets a row for it: prices 10/10/10 and weight 15 in all 12 columns (about 13% per pick, like
Mushroom or Warp Pipe; see CANNON_WEIGHTS).

CPU use of the Cannon (2c-bis stage 3): mbCapComChanceGet (fn_801C938C, used by mbCapSelectComGet and
mbCapSelectDeleteComGet) looks the orb up in the CPU orb table (0x8026753C: rows of 0x2E bytes, an orb id then 11
characters x {s16 chance, u8 condition code, pad}, ended by id -1) and returns -1 (never) when it has no row. The
table moves to section 19 (0x802FAB00; its one reference, 0x801C93AC, re-pointed) with a row for orb 8: MP7's own
row for the Cannon (MP7 main.dol 0x80296940, stride 0x32, row 5; its first 11 characters are MP6's 11), code ' '.
The orb-id switch's entry for 8 (jump table 0x802680B0) goes to a stub (0x802FAF60) that calls the board REL's
PagodaCannonComChance(player, chance) through a third hook word (0x802FAAA8; cannon.c) to adjust the chance, then
rejoins the common ending (0x801C9848: mode 0 use = chance, 1 = the table's, 2 throw away = 100 - chance).

Results: the party results screen shows the board's name label as bank `board` of mdpresult.bin's label
sprite (files 89-93, one per language; tools/pagoda/label.py). Each gets a 7th label, Pagoda Peak's (MP7's
lettering on MP6's pill), as bank 6, and mdpresultdll's `mr r5,r30` before HuSprBankSet (vanilla .text 0x18FB4)
calls a stub at 0x802FAA80: `lis r5,0x8028; lbz r5,0x3298(r5); clrlwi r5,r5,27; cmplwi r5,11; li r5,6;
beqlr; mr r5,r30; blr` (the site is found by its words: random_bonus's rebuild of the REL moves it). Everything else on that screen keeps clone_board's alias, so board 11's results
tables and save records still count under Snowflake Lake (the user's choice, 2026-11-25).

Text: MP7 bank 0x14 (Pagoda Peak's 57 records, each language from the matching MP7 messdata file, converted
by tools.pagoda.mp7_text) becomes a new bank 0x4B, after the 75 vanilla banks (messages.set_bank), so MP7
record n is message 0x4B0000 + n (PAGODA_MES in pagoda.h). The loader reads the bank count from the file
(HuWinMesDataPtrGet bounds-checks against it); splice_bank keeps appended banks when earlier steps re-run.
Until 2026-11-25 the test aid pagoda_stub appended these records to Snowflake Lake's bank 0x32 as records
26-82; this step strips them if it finds them there.

Board select (2d, page 2 of apply_party_pages_patch.py, which names the files): data/mdparty.bin gets four
files after the vanilla 254, built by tools/pagoda/select_art.py from a render of the board the user supplies
(src/orig/pagoda_screens/): 254 the empty-slot icon, 255 Pagoda Peak's octagon icon (day, night), 256 / 257
its half-disc by day / night; slot 0's banner files (0x32-0x36, one per language) get MP7's "Pagoda Peak"
lettering as bank 1. The new pictures are C8, and the vanilla half-disc pictures (0x04-0x11) are re-encoded as C8,
because the first build (RGB5A3) ran the party menu's heap out of memory (select_art.py's docstring). Bank 2 record 15 (empty in vanilla; the description of the first extra board) becomes
MP7's own board-select line (MP7 bank 8 record 5, "Climb to the top of this one-track mountain road!").
mdparty.bin is rebuilt from the original each run (no other step writes it).

Board REL: src/REL/w07Dll/*.c (built by tools/pagoda/build_pagoda_rel.py, without ninja) replaces the Snowflake
Lake copy clone_board writes as files/dll/w07dll.rel. What each event does is in its C file's header.
Character motions: MP7's fanning and chest motions (MP7 <char>.bin 0x82, 0x83, 0x89, 0x8B) become files 126-129
of each of the 11 MP6 <char>mot.bin, for Blazing Rock (pagoda.h). No other step writes those archives.
Until 2026-11-26 both were installed by the test aid pagoda_stub (retired to plans/pagoda-peak/retired/).

Outputs: build/GP6P01/main.dol, files/data/w07.bin, capsule.bin (entries 87-88), mdpresult.bin, mdparty.bin,
the 11 <char>mot.bin, files/dll/w07dll.rel, mdpresultdll.rel and files/mess/messdata*.bin (current output,
else the original; edits of existing banks work either side of this one). Deploy w07.bin to root/data/
together with the DOL: the DOL panics at start-up if the disc has no data/w07.bin, and only build_iso keeps
new files. Reads MP7 from src/orig/GP7P01/ or GP7P01.iso (tools.lib.mp7). Needs build/GP6P01/main.elf (from
ninja) and the Close Call toolchain to build the REL. Run after pagoda_peak (needs section 18). Idempotent.
Status: confirmed in Dolphin (2026-11-25) with pagoda_stub and clone_board_menu: the game boots and Pagoda Peak
plays as before from w07.bin; its text from bank 0x4B checked on a sample of lines. Snowflake Lake on its
vanilla archives and bank not yet replayed. The REL and the motions moving from pagoda_stub into this step
(2026-11-26) gave the same files byte for byte; not replayed in Dolphin since.
"""
import shutil
import struct
from dataclasses import dataclass

from PIL import Image

from tools.lib import mp7, mpdata
from tools.lib.board_tables import BOARD_NO_READS, NEW_BOARD_NO, clrlwi27
from tools.lib.dol import dol_offset, encode_branch, replace_bytes
from tools.lib import messages
from tools.lib.messages import edit_bank, set_bank
from tools.lib.paths import DATA_ORIG, DATA_OUT, DOL, MESS_NAMES, MESS_OUTPUT_DIR, MESS_SOURCE_DIR, REL_DIR
from tools.lib.ppc import ha, lo
from tools.lib.rel import R_PPC_REL24, add_calls, check_words, import_blocks, text_base, walk_relocs
from tools.pagoda import build_pagoda_rel, label, mp7_text, select_art, spaces
from tools.patches import apply_clone_board_patch as clone
from tools.patches import apply_mgtable_move_patch as mg
from tools.patches import apply_party_pages_patch as pages
from tools.patches import apply_star_trap_orb_patch as trap

# --- DOL ----------------------------------------------------------------------------------------------
SECTION = 3                     # text slot
CODE_BASE = clone.CODE_END      # 0x802FA1A0
CODE_SIZE = 0x1000
CODE_END = CODE_BASE + CODE_SIZE
PATH_ADDR = CODE_BASE           # 0x20 bytes
PATH = b"data/w07.bin"
DIR_TABLE = 0x8021BEF0
DIR_COUNT = 261                 # vanilla entries; w07 becomes dir 261
DIR_NO = DIR_COUNT
NEW_TABLE = CODE_BASE + 0x20
NEW_TABLE_END = NEW_TABLE + 8 * (DIR_COUNT + 2)
DIR_REFERENCES = (0x80007688, 0x800084A4, 0x80008BC4)   # lis, then addi at +4
POOL_OFFSET = 0x1168            # DIR_TABLE - 0x8021AD88, the base data.c keeps in a register
# addi r3,rB,0x1168 at each address, then addi r0,r4,4 and lwzx r3,r3,r0 (rB per site)
BASE_READS = {0x80007A9C: 22, 0x80008090: 26, 0x80008238: 25, 0x80008854: 23, 0x80008FF4: 22, 0x80009B6C: 29}
PATH_READ, PATH_READ_BASE = 0x80009458, 24      # slwi r0,r20,3; addi r3,r24,0x1168; lwzx r3,r3,r0
LWZX_R3 = 0x7C63002E            # lwzx r3, r3, r0
ADDI_R0_R4_4 = 0x38040004
# The orb list table (mbCapListRead): {board, capsule.bin data number} rows, ended by -1. One reference.
ORB_TABLE, ORB_ROWS = 0x80267D20, 11
ORB_REFERENCE = 0x801C7EF0      # lis r3 / addi r31,r3
NEW_ORB_TABLE = CODE_BASE + 0x860   # 0x802FAA00, after the data dir table; 13 rows
NEW_ORB_TABLE_END = NEW_ORB_TABLE + 8 * (ORB_ROWS + 2)
# Results label: mdpresultdll's `mr r5,r30` (r30 = the stored, aliased board number) before
# HuSprBankSet(group, 1, r5) becomes bl LABEL_STUB, which picks bank PAGODA_LABEL_BANK for board 11. The site
# is .text 0x18FB4 in the vanilla REL, but random_bonus rebuilds mdpresultdll and moves it (0x19118 in its
# build), so it is found by its words: lha r3,0(r31); li r4,1; mr r5,r30; bl (HuSprBankSet, relocated).
RESULT_REL = "mdpresultdll.rel"
LABEL_SITE_WORD = 0x7FC5F378    # mr r5, r30
LABEL_PATTERN = (0xA87F0000, 0x38800001, LABEL_SITE_WORD, 0x48000001)
LABEL_PATTERN_SITE = 2          # index of the hooked word in LABEL_PATTERN
LABEL_STUB = CODE_BASE + 0x8E0  # 0x802FAA80
GW_BOARD_NO = 0x80283298        # GwSystem + 8, board number in the low 5 bits
PAGODA_LABEL_BANK = 6
# The Cannon orb (orb id 8): two hook words the board REL fills (pagoda.h PAGODA_CANNON_*_HOOK), and the stubs the
# orb's event row points at.
CANNON_ID = 8
ORB_DATA, ORB_DATA_WORDS = 0x80266BDC, 10
ORB_EVENTS, ORB_EVENT_WORDS = 0x80268500, 7
CANNON_HOOKS = CODE_BASE + 0x900         # 0x802FAAA0: exec hook, kill hook
CANNON_EXEC_STUB = CODE_BASE + 0x920     # 0x802FAAC0
CANNON_KILL_STUB = CODE_BASE + 0x940     # 0x802FAAE0
HU_PRC_END = 0x8000E144
CANNON_FRAME = 0x14001C                  # the self orbs' green frame
CANNON_PRICE = 10                        # the user's choice (MP7: 20)
CANNON_GRADE = 0x43                      # 'C'
ORB_DATA_EMPTY = (0, 0, 0, 0x380022, 0xA, 0, 0, 0x5A000001, 0x802DD678, 0)
# CPU orb choice (mbCapComChanceGet fn_801C938C)
COM_TABLE, COM_ROW = 0x8026753C, 0x2E           # rows: s16 orb id, then 11 x {s16 chance, u8 code, u8 pad}
COM_REFERENCE = 0x801C93AC                      # lis r3 / addi r28,r3
COM_ROWS = 22                                   # vanilla rows before the -1 terminator
NEW_COM_TABLE = CODE_BASE + 0x960               # 0x802FAB00
NEW_COM_TABLE_END = NEW_COM_TABLE + COM_ROW * (COM_ROWS + 2)
CANNON_COM_HOOK = CANNON_HOOKS + 8              # 0x802FAAA8: PagodaCannonComChance(player, chance) or NULL
CANNON_COM_STUB = (NEW_COM_TABLE_END + 0x1F) & ~0x1F   # 0x802FAF60
COM_SWITCH, COM_SWITCH_DEFAULT = 0x802680B0, 0x801C9848   # orb-id jump table; its "no adjustment" case
COM_CODE_NONE = 0x20
# MP7's CPU row for the Cannon (MP7 orb 5), its first 11 characters (MP6's 11, same order)
CANNON_COM_CHANCES = (30, 30, 10, 50, 10, 30, 10, 10, 50, 10, 50)
ORB_EVENT_EMPTY = (0, 0, 0, 0, 0, 0xFFFFFFFF, 0)
assert NEW_TABLE_END <= NEW_ORB_TABLE and NEW_ORB_TABLE_END <= LABEL_STUB and LABEL_STUB + 0x20 <= CANNON_HOOKS
assert CANNON_HOOKS + 12 <= CANNON_EXEC_STUB and CANNON_KILL_STUB + 0x18 <= NEW_COM_TABLE
assert CANNON_COM_STUB + 0x24 <= CODE_END

# --- w07.bin --------------------------------------------------------------------------------------------
W02 = "files/data/w02.bin"
CAPSULE = "files/data/capsulechar1.bin"
MP7_ORBS = "files/data/capsule.bin"      # MP7's orb models: the Cannon orb's cannon (0x51 body, 0x50 barrel), 0x42
ARCHIVE = "w07.bin"


@dataclass(frozen=True)
class BoardFile:
    name: str | None            # pagoda.h define, or None for a file found by its offset from one
    source: str                 # an MP7 archive path, "w04" (vanilla MP6), "spaces" or "layer1"
    number: int
    kind: str = "model"         # model (HSFV037), sprite (ANM) or raw


def _mp7(name, archive, number, kind="model"):
    return BoardFile(name, archive, number, kind)


FILES = (
    BoardFile("FILE_SPACES", "spaces", spaces.MP7_SPACES_FILE, "raw"),
    BoardFile("FILE_SPACES_BELOW", "layer1", 1, "raw"),
    _mp7("FILE_MAP", W02, 6),
    BoardFile("FILE_SHOP", "w04", 5),
    BoardFile("FILE_SHOP_STAND", "w04", 6),
    BoardFile("FILE_SHOP_SMOKE", "w04", 8, "raw"),
    _mp7("FILE_KOOPA", W02, 0x35),
    *(_mp7(None, W02, n) for n in range(0x36, 0x3B)),       # his motions 1-5
    _mp7("FILE_HOUSE", W02, 0x25),
    _mp7("FILE_SIGN", W02, 0x14),
    _mp7("FILE_GONG", W02, 0x13),
    _mp7("FILE_ROCKET", W02, 0x0B),
    _mp7("FILE_ROCK", W02, 0x10),
    _mp7("FILE_CLOUD", W02, 0x26),
    _mp7("FILE_ROCK_FIRE", W02, 0x15),
    _mp7("FILE_ROCK_OUT", W02, 0x17),
    _mp7("FILE_EMITTER", W02, 0x18),
    _mp7("FILE_FAN", W02, 0x16),
    _mp7("FILE_CHEST", W02, 0x19),
    _mp7("FILE_TSHIRT", W02, 0x1A),
    _mp7("FILE_FLAME", W02, 0x2E, "sprite"),
    _mp7("FILE_SMOKE", W02, 0x30, "sprite"),
    _mp7("FILE_DRAGON", W02, 0x1B),
    _mp7("FILE_FIREBALL", W02, 0x1C),
    _mp7("FILE_FIREBALL_SPRITE", W02, 0x33, "sprite"),
    _mp7("FILE_BOWSER", CAPSULE, 0),
    *(_mp7(None, CAPSULE, n) for n in (1, 2, 8, 5, 0x10, 6, 0x11, 0x0A, 0x0B)),   # bowser.c's motion table
    _mp7("FILE_BRIDGE", W02, 0x1D),
    _mp7(None, W02, 0x1E),
    _mp7(None, W02, 0x1F),
    _mp7("FILE_BAMBOO", W02, 0x09),
    _mp7("FILE_BRANCH", W02, 0x0A),
    _mp7("FILE_CANNON", MP7_ORBS, 0x51),          # the Cannon orb's cannon body, joint "center" (cannon.c)
    _mp7("FILE_CANNON_BARREL", MP7_ORBS, 0x50),   # its barrel, hooked on the body's "center"
    _mp7("FILE_CANNON_BOOM", MP7_ORBS, 0x42),     # the explosion when there is nowhere to go
    _mp7("FILE_SCROLL", W02, 4),                  # the view-board area (MP7's mbScrollInit file)
)


def file_number(name):
    return [f.name for f in FILES].index(name)


def check_kind(blob, entry):
    if entry.kind == "sprite":
        mpdata.parse_anm(blob)      # raises on a file that isn't a sprite animation
    elif entry.kind == "model" and not blob.startswith(b"HSFV037"):
        raise RuntimeError(f"{entry.source} file {entry.number:#x} is not an HSFV037 model")


def board_files():
    """The decompressed contents of every file of w07.bin, in order."""
    archives = {}

    def archive(source):
        if source not in archives:
            if source == "w04":
                archives[source] = mpdata.read_archive(DATA_ORIG / "w04.bin")
            else:
                data = mp7.read(source)
                count = struct.unpack_from(">I", data, 0)[0]
                archives[source] = (data, list(struct.unpack_from(f">{count}I", data, 4)))
        return archives[source]

    out = []
    for entry in FILES:
        if entry.source == "spaces":
            blob = spaces.mp7_spaces()
        elif entry.source == "layer1":
            blob = spaces.mp7_layer1(entry.number)
        else:
            blob = mpdata.read_file(*archive(entry.source), entry.number)
        check_kind(blob, entry)
        out.append(bytes(blob))
    return out


def write_archive():
    data, _ = mpdata.append_files(struct.pack(">I", 0), [], board_files())
    out = DATA_OUT / ARCHIVE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"data/{ARCHIVE}: {len(FILES)} files, {len(data)} bytes (data dir {DIR_NO})")


# --- messages ---------------------------------------------------------------------------------------------
BANK = 0x4B                     # after the 75 vanilla banks (0x00-0x4A)
MP7_BANK, MP7_RECORDS = 0x14, 57
OLD_BANK, OLD_BANK_RECORDS = 0x32, 26   # Snowflake Lake's bank, where pagoda_stub used to append the text
MP7_ORB_BANK, MP7_CANNON_NAME, MP7_CANNON_DESC = 0x1B, 71, 5
CANNON_NAME_RECORD, CANNON_DESC_RECORD = MP7_RECORDS, MP7_RECORDS + 1     # 57, 58
ORB_NAME_HEADER = bytes.fromhex("00070001")   # every MP6 orb name (bank 56)
DESC_BANK, DESC_RECORDS = 2, 18                # board select: names 0-8, descriptions 9-14, 15-17 empty
MP7_SELECT_BANK, MP7_SELECT_DESC = 0x8, 5      # MP7's board select line for Pagoda Peak
DESC_WIDTH = 0x15                              # MP6's description records: 00 15 00 <lines>


def pagoda_records(name):
    records = mp7_text.bank_records(mp7.read(f"files/mess/{name}"), MP7_BANK)
    if len(records) != MP7_RECORDS:
        raise RuntimeError(f"MP7 {name}: bank {MP7_BANK:#x} has {len(records)} records, expected {MP7_RECORDS}")
    return [mp7_text.convert(record) for record in records]


def cannon_records(name):
    """The Cannon's name (with MP6's orb-name header) and description, from MP7's orb bank."""
    mp7_mess = mp7.read(f"files/mess/{name}")
    orbs = mp7_text.bank_records(mp7_mess, MP7_ORB_BANK)
    name_record = mp7_text.convert(orbs[MP7_CANNON_NAME])
    return [ORB_NAME_HEADER + name_record[4:], mp7_text.convert(orbs[MP7_CANNON_DESC])]


def select_description(name):
    """MP7's board select line for Pagoda Peak as an MP6 description record (header 00 15 00 <lines>)."""
    record = mp7_text.bank_records(mp7.read(f"files/mess/{name}"), MP7_SELECT_BANK)[MP7_SELECT_DESC]
    body = mp7_text.convert(record)[4:]
    lines = body.rstrip(b"\0").count(b"\n") + 1
    return struct.pack(">HH", DESC_WIDTH, lines) + body


def write_messages():
    record = pages.DESC_FIRST + next(i for i, b in enumerate(pages.EXTRA_BOARDS) if b.board_no == NEW_BOARD_NO)
    for name in MESS_NAMES:
        out = MESS_OUTPUT_DIR / name
        source = out if out.exists() else MESS_SOURCE_DIR / name
        records = pagoda_records(name)
        data = edit_bank(source.read_bytes(), {}, f"pagoda_board {name}", bank=OLD_BANK,
                         bank_records=OLD_BANK_RECORDS, known_tails=[records])
        # bank 0x4B: MP7 Pagoda Peak's 57 records, then the Cannon's name and description (57, 58); an earlier
        # build had only the 57
        data = set_bank(data, BANK, records + cannon_records(name), f"pagoda_board {name}", known=[records])
        # the board select description (bank 2 record 15: empty in vanilla)
        desc = select_description(name)
        vanilla = messages.bank_records((MESS_SOURCE_DIR / name).read_bytes(), DESC_BANK)[record]
        if messages.bank_records(data, DESC_BANK)[record] not in (vanilla, desc):
            raise RuntimeError(f"pagoda_board {name}: bank {DESC_BANK} record {record} is already in use")
        data = edit_bank(data, {record: desc}, f"pagoda_board {name}", bank=DESC_BANK, bank_records=DESC_RECORDS)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    print(f"mess/messdata*.bin: MP7 bank {MP7_BANK:#x} ({MP7_RECORDS} records) as bank {BANK:#x}; "
          f"bank {OLD_BANK:#x} back to its {OLD_BANK_RECORDS} records; board select description as bank "
          f"{DESC_BANK} record {record}")


# --- DOL ----------------------------------------------------------------------------------------------
def add_section(dol):
    """Text section SECTION at CODE_BASE (zero-filled); the arena clamp moves up to CODE_END."""
    if struct.unpack_from(">I", dol, 0x48 + 4 * clone.SECTION)[0] != clone.CODE_BASE:
        raise SystemExit("DOL section 18 is missing: run apply_clone_board_patch.py first")
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
        print(f"Added DOL section 19 (text slot {SECTION}): {CODE_BASE:#010x}-{CODE_END:#010x}")
    at = dol_offset(dol, mg.ARENA_CAVE)
    hi, low = struct.unpack_from(">2I", dol, at)
    if hi >> 16 != 0x3C00 or low >> 16 != 0x6000:
        raise RuntimeError("OSSetArenaLo clamp not found: run apply_mgtable_move_patch.py first")
    if ((hi & 0xFFFF) << 16 | (low & 0xFFFF)) < CODE_END:
        struct.pack_into(">2I", dol, at, 0x3C000000 | (CODE_END >> 16), 0x60000000 | (CODE_END & 0xFFFF))
        print(f"OSSetArenaLo now clamps ArenaLo to >= {CODE_END:#010x}")


def section_blob(dol):
    """The path string and the moved table, built from the vanilla table (which stays unchanged in `dol`)."""
    start = dol_offset(dol, DIR_TABLE)
    entries = [struct.unpack_from(">Ii", dol, start + 8 * i) for i in range(DIR_COUNT + 1)]
    if any(path == 0 or num != -1 for path, num in entries[:-1]) or entries[-1][0] != 0:
        raise RuntimeError(f"Unexpected data dir table at {DIR_TABLE:#010x}")
    blob = PATH.ljust(NEW_TABLE - PATH_ADDR, b"\0")
    blob += bytes(dol[start:start + 8 * DIR_COUNT])
    blob += struct.pack(">Ii", PATH_ADDR, -1)
    blob += bytes(dol[start + 8 * DIR_COUNT:start + 8 * (DIR_COUNT + 1)])
    assert len(blob) == NEW_TABLE_END - PATH_ADDR
    return blob


def repoint(dol, lis_address, old=DIR_TABLE, new=NEW_TABLE):
    """Point the lis/addi pair at lis_address from table `old` to `new` (accepts either)."""
    for address, old_imm, new_imm in ((lis_address, ha(old), ha(new)),
                                      (lis_address + 4, lo(old), lo(new))):
        word = struct.unpack_from(">I", dol, dol_offset(dol, address))[0]
        original = (word & 0xFFFF0000) | old_imm
        patched = (word & 0xFFFF0000) | new_imm
        replace_bytes(dol, dol_offset(dol, address), struct.pack(">I", original), struct.pack(">I", patched),
                      f"table reference at {address:#010x}")


def addis(rd, ra, imm):
    return (15 << 26) | (rd << 21) | (ra << 16) | (imm & 0xFFFF)


def addi(rd, ra, imm):
    return (14 << 26) | (rd << 21) | (ra << 16) | (imm & 0xFFFF)


def lwz(rd, ra, disp):
    return (32 << 26) | (rd << 21) | (ra << 16) | (disp & 0xFFFF)


def slwi(ra, rs, n):
    return (21 << 26) | (rs << 21) | (ra << 16) | (n << 11) | (31 - n) << 1


def base_read_words():
    """{address: (original three words, patched three words)} for the base-register reads."""
    entry = NEW_TABLE + 4
    out = {site: ((addi(3, base, POOL_OFFSET), ADDI_R0_R4_4, LWZX_R3),
                  (addis(3, 4, ha(entry)), ADDI_R0_R4_4, lwz(3, 3, lo(entry))))
           for site, base in BASE_READS.items()}
    out[PATH_READ] = ((slwi(0, 20, 3), addi(3, PATH_READ_BASE, POOL_OFFSET), LWZX_R3),
                      (slwi(3, 20, 3), addis(3, 3, ha(NEW_TABLE)), lwz(3, 3, lo(NEW_TABLE))))
    return out


def orb_rows(dol):
    """The moved orb list table: the vanilla rows, {11, ORB_LIST}, the terminator."""
    start = dol_offset(dol, ORB_TABLE)
    rows = [struct.unpack_from(">iI", dol, start + 8 * i) for i in range(ORB_ROWS + 1)]
    if [r[0] for r in rows] != list(range(ORB_ROWS)) + [-1]:
        raise RuntimeError(f"Unexpected orb list table: {rows}")
    rows = rows[:-1] + [(NEW_BOARD_NO, ORB_LIST), rows[-1]]
    return b"".join(struct.pack(">iI", *r) for r in rows)


def label_stub():
    return [0x3C000000 | (5 << 21) | (GW_BOARD_NO >> 16),              # lis r5, 0x8028
            (34 << 26) | (5 << 21) | (5 << 16) | (GW_BOARD_NO & 0xFFFF),  # lbz r5, 0x3298(r5)
            clrlwi27(5, 5),
            (10 << 26) | (5 << 16) | NEW_BOARD_NO,                       # cmplwi r5, 11
            (14 << 26) | (5 << 21) | PAGODA_LABEL_BANK,                  # li r5, 6
            0x4D820020,                                                  # beqlr
            LABEL_SITE_WORD,                                             # mr r5, r30
            0x4E800020]                                                  # blr


def cannon_stubs():
    """(exec stub, kill stub) words: jump through the hook word, or end the process / return when it is NULL."""
    def load(hook):
        return [0x3D800000 | ha(hook), (32 << 26) | (12 << 21) | (12 << 16) | lo(hook)]   # lis r12; lwz r12,lo(r12)
    cmpwi_r12_0, mtctr_r12, bctr = 0x2C0C0000, 0x7D8903A6, 0x4E800420
    exec_stub = load(CANNON_HOOKS) + [cmpwi_r12_0, 0x4182000C, mtctr_r12, bctr]      # beq +12 -> b HuPrcEnd
    exec_stub.append(encode_branch(CANNON_EXEC_STUB + 4 * len(exec_stub), HU_PRC_END))
    kill_stub = load(CANNON_HOOKS + 4) + [cmpwi_r12_0, 0x4D820020, mtctr_r12, bctr]  # beqlr
    return exec_stub, kill_stub


def com_table(dol):
    """The CPU orb table with the Cannon's row added before the terminator."""
    start = dol_offset(dol, COM_TABLE)
    rows = [bytes(dol[start + COM_ROW * i:start + COM_ROW * (i + 1)]) for i in range(COM_ROWS + 1)]
    ids = [struct.unpack_from(">h", row)[0] for row in rows]
    if ids[-1] != -1 or -1 in ids[:-1] or CANNON_ID in ids:
        raise RuntimeError(f"Unexpected CPU orb table: ids {ids}")
    cannon = struct.pack(">h", CANNON_ID) + b"".join(struct.pack(">hBB", c, COM_CODE_NONE, 0) for c in CANNON_COM_CHANCES)
    assert len(cannon) == COM_ROW
    return b"".join(rows[:-1]) + cannon + rows[-1]


def com_stub():
    """Call PagodaCannonComChance(r31 player, r30 chance) through the hook word, keep its result as the chance, rejoin
    the common ending; without a hook just rejoin it."""
    words = [0x3D800000 | ha(CANNON_COM_HOOK), (32 << 26) | (12 << 21) | (12 << 16) | lo(CANNON_COM_HOOK),
             0x2C0C0000,                 # cmpwi r12, 0
             0x41820018,                 # beq +24 -> b default
             0x7FE3FB78,                 # mr r3, r31
             0x7FC4F378,                 # mr r4, r30
             0x7D8903A6,                 # mtctr r12
             0x4E800421,                 # bctrl
             0x7C7E1B78]                 # mr r30, r3
    words.append(encode_branch(CANNON_COM_STUB + 4 * len(words), COM_SWITCH_DEFAULT))
    return words


def cannon_rows():
    """The Cannon's orb data and event rows."""
    data = (CANNON_MODEL, CANNON_FRAME, (BANK << 16) | CANNON_DESC_RECORD, (BANK << 16) | CANNON_NAME_RECORD, 0, 0,
            CANNON_PRICE, CANNON_GRADE << 24, ORB_DATA_EMPTY[8], 0x01000000)
    event = (CANNON_EXEC_STUB, CANNON_KILL_STUB, 0, 2, 0, 0xFFFFFFFF, 0)
    return data, event


def write_new(dol, address, blob, what):
    start = dol_offset(dol, address)
    if bytes(dol[start:start + len(blob)]) not in (bytes(len(blob)), blob):
        raise RuntimeError(f"Section 19 at {address:#010x} ({what}) holds unexpected bytes")
    dol[start:start + len(blob)] = blob


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    add_section(dol)
    blob = section_blob(dol)
    start = dol_offset(dol, PATH_ADDR)
    if bytes(dol[start:start + len(blob)]) not in (b"\0" * len(blob), blob):
        raise RuntimeError(f"Section 19 at {PATH_ADDR:#010x} holds unexpected bytes")
    dol[start:start + len(blob)] = blob
    for site in DIR_REFERENCES:
        repoint(dol, site)
    for site, (original, patched) in base_read_words().items():
        replace_bytes(dol, dol_offset(dol, site), struct.pack(">3I", *original), struct.pack(">3I", *patched),
                      f"data dir table read at {site:#010x}")
    write_new(dol, NEW_ORB_TABLE, orb_rows(dol), "orb list table")
    repoint(dol, ORB_REFERENCE, ORB_TABLE, NEW_ORB_TABLE)
    read = next(r for r in BOARD_NO_READS if r.name == "orb_list")
    replace_bytes(dol, dol_offset(dol, read.where),
                  struct.pack(">I", encode_branch(read.where, clone.stub_address(read.rd, read.rs), link=True)),
                  struct.pack(">I", clrlwi27(read.rd, read.rs)), "orb list board read (clone board alias)")
    write_new(dol, LABEL_STUB, struct.pack(">8I", *label_stub()), "results label stub")
    hooks = dol_offset(dol, CANNON_HOOKS)
    if bytes(dol[hooks:hooks + 12]) != bytes(12):
        raise RuntimeError(f"Section 19 at {CANNON_HOOKS:#010x} (Cannon hooks) is not zero")
    exec_stub, kill_stub = cannon_stubs()
    write_new(dol, CANNON_EXEC_STUB, struct.pack(f">{len(exec_stub)}I", *exec_stub), "Cannon exec stub")
    write_new(dol, CANNON_KILL_STUB, struct.pack(f">{len(kill_stub)}I", *kill_stub), "Cannon kill stub")
    write_new(dol, NEW_COM_TABLE, com_table(dol), "CPU orb table")
    repoint(dol, COM_REFERENCE, COM_TABLE, NEW_COM_TABLE)
    stub = com_stub()
    write_new(dol, CANNON_COM_STUB, struct.pack(f">{len(stub)}I", *stub), "Cannon CPU stub")
    entry = dol_offset(dol, COM_SWITCH + 4 * CANNON_ID)
    replace_bytes(dol, entry, struct.pack(">I", COM_SWITCH_DEFAULT), struct.pack(">I", CANNON_COM_STUB),
                  "CPU orb switch entry for the Cannon")
    data, event = cannon_rows()
    for table, words, empty, row in ((ORB_DATA, ORB_DATA_WORDS, ORB_DATA_EMPTY, data),
                                     (ORB_EVENTS, ORB_EVENT_WORDS, ORB_EVENT_EMPTY, event)):
        at = dol_offset(dol, table + 4 * words * CANNON_ID)
        replace_bytes(dol, at, struct.pack(f">{words}I", *empty), struct.pack(f">{words}I", *row),
                      f"orb {CANNON_ID} row of {table:#010x}")
    DOL.write_bytes(dol)
    print(f"main.dol: data dir table moved to {NEW_TABLE:#010x} with dir {DIR_NO} = {PATH.decode()}")


# --- orb list and results --------------------------------------------------------------------------
CAPSULE = "capsule.bin"
CAPSULE_ENTRIES = 87            # vanilla 85 + star_trap_orb's model (85) + castaway_wheel's (86)
ORB_LIST = 0x140000 | CAPSULE_ENTRIES     # entry 87
CANNON_MODEL = ORB_LIST + 1               # entry 88: MP7 capsule.bin file 5
MP7_CAPSULE, MP7_CANNON_MODEL = "files/data/capsule.bin", 5
# An orb list row: orb id, 3 prices, then 12 signed weights, 4 ranks (1st-4th) each for: orb spaces in the first
# half of the game (mbCapMasuNextGet, columns 0-3), orb spaces in the second half (4-7), the shop (CapShopNextGet,
# 8-11; an orb the player holds counts half, and an orb is offered once per visit). MP7's columns mean something
# else (its Cannon row, 05 14 14 0a 0a 0a 0a 14 0a 0a 14 1e 1e 14 00 00, gave 0% in the shop for 3rd and 4th).
# The other orbs on Pagoda Peak's list weigh about 100 per column, so a weight w is about w / (100 + w) of a pick.
# The user's choice (2026-11-25, after testing at 120): 15 everywhere, about 13%, like a regular orb.
CANNON_WEIGHTS = (15,) * 12
ORB_SOURCE = 0x4D               # Snowflake Lake's list (orb list table row 3)
ORB_ROW = 16                    # orb id, 3 prices, 12 weights; a row starting 0xFF ends the list
REMOVED_ORBS = (0x1E,)          # Snack
MDPRESULT = "mdpresult.bin"
MDPARTY = "mdparty.bin"


def cannon_row():
    """The Cannon's row: the user's price (10 in every price column) and CANNON_WEIGHTS."""
    return bytes([CANNON_ID]) + bytes([CANNON_PRICE] * 3) + bytes(CANNON_WEIGHTS)


def orb_list(source):
    """`source` (an orb list file) without the rows of REMOVED_ORBS, with the Cannon's row added in id order."""
    rows = [source[i:i + ORB_ROW] for i in range(0, len(source), ORB_ROW)]
    end = next(i for i, row in enumerate(rows) if row[0] == 0xFF)
    kept = [row for row in rows[:end] if row[0] not in REMOVED_ORBS]
    if len(kept) != end - len(REMOVED_ORBS) or any(row[0] == CANNON_ID for row in kept):
        raise RuntimeError("Snowflake Lake's orb list isn't the one this patch was written against")
    kept = sorted(kept + [cannon_row()], key=lambda row: row[0])
    return b"".join(kept + rows[end:])


def is_orb_list(payload):
    """True for an orb list file: 16-byte rows, the last one starting 0xFF."""
    return len(payload) % ORB_ROW == 0 and len(payload) >= ORB_ROW and payload[-ORB_ROW] == 0xFF


def mp7_cannon_model():
    model = spaces.mp7_file(MP7_CAPSULE, MP7_CANNON_MODEL)
    if not model.startswith(b"HSFV037"):
        raise RuntimeError(f"MP7 capsule.bin file {MP7_CANNON_MODEL} is not an HSFV037 model")
    return model


def write_orb_list():
    out = DATA_OUT / CAPSULE
    source = out if out.exists() else DATA_ORIG / CAPSULE
    entries = trap.capsule_entries(source.read_bytes())
    vanilla, offsets = mpdata.read_archive(DATA_ORIG / CAPSULE)
    ours = [trap.compress_entry(orb_list(mpdata.read_file(vanilla, offsets, ORB_SOURCE))),
            trap.compress_entry(mp7_cannon_model())]
    if not CAPSULE_ENTRIES <= len(entries) <= CAPSULE_ENTRIES + len(ours):
        raise SystemExit(f"{source}: {len(entries)} entries, expected {CAPSULE_ENTRIES} "
                         "(run apply_star_trap_orb_patch.py and apply_castaway_wheel_patch.py first)")
    # entries after castaway_wheel's are an earlier build of this step: the orb list, then the Cannon model
    for i, entry in enumerate(entries[CAPSULE_ENTRIES:]):
        payload = mpdata.read_file(trap.pack_capsule([entry]), [8], 0)
        if not (is_orb_list(payload) if i == 0 else payload.startswith(b"HSFV037")):
            raise RuntimeError(f"{source}: entry {CAPSULE_ENTRIES + i} is not one of pagoda_board's")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(trap.pack_capsule(entries[:CAPSULE_ENTRIES] + ours))
    print(f"data/{CAPSULE}: Pagoda Peak's orb list as entry {CAPSULE_ENTRIES} ({ORB_LIST:#x}), Snowflake Lake's "
          f"without orb(s) {', '.join(hex(o) for o in REMOVED_ORBS)} plus the Cannon; the Cannon model "
          f"(MP7 capsule.bin {MP7_CANNON_MODEL}) as entry {CAPSULE_ENTRIES + 1} ({CANNON_MODEL:#x})")


def write_board_select():
    """mdparty.bin from the original: the page-2 files appended and Pagoda Peak's banner bank (module docstring)."""
    data, offsets = mpdata.read_archive(DATA_ORIG / MDPARTY)
    if len(offsets) != pages.MDPARTY_FILES:
        raise RuntimeError(f"{MDPARTY}: {len(offsets)} files, expected {pages.MDPARTY_FILES}")
    index = next(i for i, b in enumerate(pages.EXTRA_BOARDS) if b.board_no == NEW_BOARD_NO)
    board = pages.EXTRA_BOARDS[index]
    order = (pages.EMPTY_ICON, board.icon, board.disc_day, board.disc_night)
    if list(order) != list(range(pages.MDPARTY_FILES, pages.NEW_FILES)):
        raise RuntimeError("apply_party_pages_patch.py's file numbers no longer match this step's")
    disc = select_art.DISC_FILE
    blobs = {i: mpdata.read_file(data, offsets, i) for i in (*select_art.ICON_FILES, disc, disc + 1)}
    icons = [select_art.image(blobs[i]) for i in select_art.ICON_FILES]
    render = select_art.load_render()
    day, night = select_art.disc_pictures(render, select_art.image(blobs[disc]))
    icon_blob = blobs[select_art.ICON_FILES[0]]
    half, full = select_art.HALF, (0, 0, select_art.HALF, select_art.HALF)
    ew, eh = select_art.EMPTY_SIZE
    empty = select_art.empty_picture(icons).resize(select_art.EMPTY_SIZE, Image.LANCZOS)
    new = [select_art.c8_sprite(icon_blob, empty, [(0, 0, ew // 2, eh), (ew // 2, 0, ew // 2, eh)]),
           select_art.c8_sprite(icon_blob, select_art.icon_picture(render, icons),
                                [full, (half, 0, half, half)]),
           select_art.c8_sprite(blobs[disc], day, [full]),
           select_art.c8_sprite(blobs[disc + 1], night, [full])]
    # memory: the vanilla half-discs and sun / moon as C8 too (select_art's docstring)
    for number in select_art.VANILLA_DISCS:
        blob = mpdata.read_file(data, offsets, number)
        data, offsets = mpdata.replace_file(data, offsets, number,
                                            select_art.c8_sprite(blob, select_art.image(blob), [full]))
    slot, page = index % pages.SLOTS, 1 + index // pages.SLOTS
    first = select_art.BANNER_FIRST + select_art.LANGUAGES * slot
    for language, language_file in enumerate(label.LABEL_FILES.values()):
        number = first + language
        blob = mpdata.read_file(data, offsets, number)
        if select_art.bank_count(blob) != page:
            raise RuntimeError(f"{MDPARTY} file {number:#x}: {select_art.bank_count(blob)} banks, expected {page}")
        w, h = select_art.bitmap(blob)[:2]
        banner = select_art.banner_picture(label.mp7_name(language_file), (w, h))
        data, offsets = mpdata.replace_file(data, offsets, number, select_art.add_bank(blob, banner))
    data, offsets = mpdata.append_files(data, offsets, new)
    out = DATA_OUT / MDPARTY
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"data/{MDPARTY}: board select files {pages.MDPARTY_FILES}-{pages.NEW_FILES - 1} (empty icon, Pagoda "
          f"Peak's icon, half-disc day / night) and its banner as bank {page} of files {first:#x}-{first + 4:#x}; "
          f"half-discs {select_art.VANILLA_DISCS[0]:#x}-{select_art.VANILLA_DISCS[-1]:#x} as C8")


def write_labels():
    out = DATA_OUT / MDPRESULT
    data, offsets = mpdata.read_archive(out if out.exists() else DATA_ORIG / MDPRESULT)
    vanilla, vanilla_offsets = mpdata.read_archive(DATA_ORIG / MDPRESULT)
    for number, language_file in label.LABEL_FILES.items():
        original = mpdata.read_file(vanilla, vanilla_offsets, number)
        patched = label.label_sprite(original, language_file)
        if mpdata.read_file(data, offsets, number) not in (original, patched):
            raise RuntimeError(f"{MDPRESULT} file {number} is neither vanilla nor Pagoda Peak's label sprite")
        data, offsets = mpdata.replace_file(data, offsets, number, patched)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"data/{MDPRESULT}: Pagoda Peak's results label as bank {PAGODA_LABEL_BANK} of files "
          f"{min(label.LABEL_FILES)}-{max(label.LABEL_FILES)}")


def label_site(rel):
    """.text offset of the results label hook: the existing call to LABEL_STUB, else the one match of
    LABEL_PATTERN."""
    hooked = [cursor for _, section, cursor, kind, _, addend in walk_relocs(rel, import_blocks(rel)[0])
              if section == 1 and kind == R_PPC_REL24 and addend == LABEL_STUB]
    if hooked:
        return hooked[0]
    base, pattern = text_base(rel), struct.pack(f">{len(LABEL_PATTERN)}I", *LABEL_PATTERN)
    hits, at = [], rel.find(pattern, base)
    while at != -1:
        hits.append(at - base + 4 * LABEL_PATTERN_SITE)
        at = rel.find(pattern, at + 4)
    if len(hits) != 1:
        raise RuntimeError(f"{RESULT_REL}: the results label site matches {len(hits)} times, expected once")
    return hits[0]


def hook_results():
    path = REL_DIR / RESULT_REL
    if not path.exists():
        raise SystemExit(f"{path} is missing: run apply_clone_board_patch.py first")
    rel = bytearray(path.read_bytes())
    site = label_site(rel)
    check_words(rel, site, f"{LABEL_SITE_WORD:08X}", "48000001")
    added = add_calls(rel, [(site, LABEL_STUB)])
    path.write_bytes(rel)
    print(f"{RESULT_REL}: .text {site:#x} calls the results label stub ({added} new)")


# --- Board REL and character motions ----------------------------------------------------------------
CHARS = ("mario", "luigi", "peach", "yoshi", "wario", "daisy", "waluigi", "kinopio", "teresa", "minikoopa",
         "kinopiko")
CHAR_MOTS = 126                               # files in every vanilla <char>mot.bin
MP7_CHAR_MOTS = (0x82, 0x83, 0x89, 0x8B)      # MP7 <char>.bin: fan slow, fan fast, hold chest, carry chest


def mp7_char_motions(char):
    data = mp7.read(f"files/data/{char}.bin")
    count = struct.unpack_from(">I", data, 0)[0]
    offsets = list(struct.unpack_from(f">{count}I", data, 4))
    return [mpdata.read_file(data, offsets, i) for i in MP7_CHAR_MOTS]


def write_char_motions():
    """MP7's four motions as files 126-129 of every <char>mot.bin (current output, else the original)."""
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    for char in CHARS:
        name = f"{char}mot.bin"
        out = DATA_OUT / name
        data, offsets = mpdata.read_archive(out if out.exists() else DATA_ORIG / name)
        if len(offsets) not in (CHAR_MOTS, CHAR_MOTS + len(MP7_CHAR_MOTS)):
            raise RuntimeError(f"{name}: {len(offsets)} files, expected {CHAR_MOTS} "
                               f"or {CHAR_MOTS + len(MP7_CHAR_MOTS)}")
        data, offsets = mpdata.keep_files(data, offsets, CHAR_MOTS)
        data, offsets = mpdata.append_files(data, offsets, mp7_char_motions(char))
        out.write_bytes(data)


def install_rel():
    """Board 11's own REL (src/REL/w07Dll, tools/pagoda/build_pagoda_rel.py) over clone_board's w07dll.rel."""
    built = build_pagoda_rel.build()
    out = REL_DIR / clone.REL_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(built, out)
    print(f"Board 11: Pagoda Peak REL installed as {out} ({out.stat().st_size} bytes)")


def main():
    if not DOL.exists():
        raise SystemExit(f"{DOL} is missing: build the DOL first")
    patch_dol()
    write_archive()
    write_messages()
    write_orb_list()
    write_labels()
    hook_results()
    write_board_select()
    write_char_motions()
    install_rel()


if __name__ == "__main__":
    main()
