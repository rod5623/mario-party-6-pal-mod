"""E. Gadd's Garage: the Castaway Wheel o' Fortune above space 7.

Same event as apply_castaway_wheel_patch.py: whenever any player enters space 7 (blue, the left end of the
bottom-right conveyor, between the orb ring 5 and the platform 6; boards/E. Gadd's Garage/e-gadds-garage.md),
on every pass, the wheel spins automatically and one of four slices is applied: a random orb (Castaway's pool),
+10 coins, -10 coins, or a teleport to a random "?", miracle, duel or DK/Bowser space (none excluded here). The
same floating wheel model turns above the space.

Reused as is (already in the DOL and data): the Castaway spin cave (icon swap + Faire's roulette), its random orb
routine, the icons in every board*.bin and the wheel model (capsule.bin 0x140056).

New:
  * Space 7 gets flag 0x200000 in root/data/w02.bin and w02n.bin. (0x4000 as on Castaway is NOT free here: on
    w02 the field 0xC000 numbers the steam pistons, spaces 31-33.)
  * w02Dll .text 0x3A0C, `mr r29,r4` at the start of the pass handler fn_1_39F4 (registered with
    mbev_MasuMoveEndSet; r3 = player, r4 = space). The handler drops r3 before its exit, so the hook is at the
    entry: a module-0 call to CAVE_PASS, which runs the Castaway pass body and ends with the displaced
    `mr r29,r4`.
  * w02Dll .text 0x1B44, `bl mbMapCameraSet` (the last call of the board init fn_1_F4), retargeted to CAVE_INIT:
    create the wheel model, then make the original call.
  * Copies of the show / outcome / teleport / model / turn caves with E. Gadd's bank, speaker and position, in
    DOL section 16 after the Castaway troll.
  * Text: bank 0x30 records 27-33 (27 records originally), English in every language file, speaker 0xE (E. Gadd).

Run after apply_castaway_troll_patch.py (section 16 and the shared Castaway caves). Idempotent.
Not run in Dolphin.
"""
import shutil
import struct

from tools.patches import apply_castaway_spare_change_patch as spare
from tools.patches import apply_castaway_troll_patch as troll
from tools.patches import apply_castaway_wheel_patch as cw
from tools.patches import apply_wheel_of_fortune_patch as wheel
from tools.lib import mpdata
from tools.lib.paths import DOL
from tools.lib.dol import dol_offset
from tools.lib.boards import load_spaces, replace_file0
from tools.lib.paths import MESS_NAMES, MESS_OUTPUT_DIR, MESS_SOURCE_DIR, REL_DIR, REL_ORIG
from tools.patches.apply_star_shuffle_bet_patch import edit_bank
from tools.lib.ppc import Asm, BLR, LWZ, MFLR, MTLR, STW, STWU, i_addi, i_mem, i_mr
from tools.lib.boards import flag_offset
from tools.lib.paths import BACKUPS, GAME_DATA
from tools.lib.rel import add_calls, check_words, import_blocks, retarget_call, walk_relocs

REL_NAME = "w02Dll.rel"
BOARDS = ("w02", "w02n")
TRIGGER_SPACE = 7
TRIGGER_FLAG = 0x200000         # unused by w02Dll and the main DOL (see the module docstring)
SITE_PASS = 0x3A0C              # w02Dll .text: `mr r29,r4` near the start of fn_1_39F4
WORD_PASS = "7C9D2378"
SITE_INIT = 0x1B44              # w02Dll .text: bl mbMapCameraSet, the last call of fn_1_F4

# DOL section 16 (apply_castaway_spare_change_patch.py), after the troll's code
CAVE_SHOW = 0x802F87C0          # 0x40
CAVE_PASS = 0x802F8800          # 0x100 of code, then the hold floats (0.0, 8.0)
CAVE_FLOATS = CAVE_PASS + 0x100
CAVE_OUTCOME = 0x802F8920       # 0x140
CAVE_TELEPORT = 0x802F8A60      # 0x180
CAVE_MODEL = 0x802F8BE0         # 0xA0
CAVE_TURN = 0x802F8C80          # 0x80
CAVE_INIT = 0x802F8D00          # 0x50
CAVE_DATA = 0x802F8D50          # position, spin step, model id, angle, zero (0x20)
USED_END = CAVE_DATA + 0x20
assert troll.USED_END <= CAVE_SHOW and USED_END <= spare.CODE_END

WHEEL_POS = (-399.0, -149.0 + 225.0, 1.0)  # space 7 is at (-399, -149, 1); 225 above it, as on Castaway
SPIN_STEP = cw.SPIN_STEP

BANK = 0x30
BANK_RECORDS = 27
MSG_BASE = 0x300000
MSG_INTRO = BANK_RECORDS        # 27; then 28-31 the outcome lines for slices 0-3
MSG_FULL = MSG_INTRO + 5        # 32
MSG_NO_COINS = MSG_INTRO + 6    # 33
SPEAKER = 0xE                   # E. Gadd, as in every w02 event
TEXT = cw.TEXT[:7]              # the Castaway lines without the unused "No Stars to lose" line
RECORDS = cw.records(TEXT)


def build_pass(address):
    """Called from the start of fn_1_39F4 (r3 = player, r4 = space). Runs the wheel on space 7, then the
    displaced `mr r29,r4`. fn_1_39F4 has saved r29 already and reloads r3/r4 afterwards."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 30, 1, 0x18))
    a.word(i_mem(STW, 31, 1, 0x1C))
    a.word(i_mr(30, 3))
    a.word(i_mr(31, 4))
    cw.pass_body(a, CAVE_SHOW, cw.CAVE_SPIN, CAVE_OUTCOME, floats=CAVE_FLOATS, flag=TRIGGER_FLAG, intro=MSG_INTRO)
    a.label("return")
    a.word(i_mr(29, 31))  # the displaced instruction (r4 = space)
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(i_mem(LWZ, 30, 1, 0x18))
    a.word(i_mem(LWZ, 31, 1, 0x1C))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.word(BLR)
    code = a.assemble()
    if len(code) > CAVE_FLOATS - CAVE_PASS:
        raise RuntimeError(f"pass cave is {len(code):#x} bytes, too big")
    return code


def pieces():
    return {
        CAVE_SHOW: cw.build_show(CAVE_SHOW, msg_base=MSG_BASE, speaker=SPEAKER),
        CAVE_PASS: build_pass(CAVE_PASS).ljust(CAVE_FLOATS - CAVE_PASS, b"\0") + struct.pack(">ff", 0.0, 8.0),
        CAVE_OUTCOME: cw.build_outcome(CAVE_OUTCOME, CAVE_SHOW, CAVE_TELEPORT, intro=MSG_INTRO, full=MSG_FULL,
                                       no_coins=MSG_NO_COINS, limit=CAVE_TELEPORT - CAVE_OUTCOME),
        CAVE_TELEPORT: cw.build_teleport(CAVE_TELEPORT, excluded=(), limit=CAVE_MODEL - CAVE_TELEPORT),
        CAVE_MODEL: cw.build_model(CAVE_MODEL, data=CAVE_DATA, turn=CAVE_TURN, limit=CAVE_TURN - CAVE_MODEL),
        CAVE_TURN: cw.build_turn(CAVE_TURN, data=CAVE_DATA, limit=CAVE_INIT - CAVE_TURN),
        CAVE_INIT: cw.build_init_hook(CAVE_INIT, model=CAVE_MODEL, limit=CAVE_DATA - CAVE_INIT),
        CAVE_DATA: struct.pack(">3ffIff", *WHEEL_POS, SPIN_STEP, 0, 0.0, 0.0),
    }


def rel_hooked(data):
    from tools.patches import apply_egadd_robots_patch as robots
    block = import_blocks(data)[0]
    return any(section == 1 and cursor == SITE_PASS and addend in (CAVE_PASS, robots.CAVE_PASS)
               for _, section, cursor, _, _, addend in walk_relocs(data, block))


def rel_data():
    path = REL_DIR / REL_NAME
    return bytearray((path if path.exists() else REL_ORIG / REL_NAME).read_bytes())


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    if struct.unpack_from(">I", dol, 0x48 + 4 * spare.SECTION)[0] != spare.CODE_BASE:
        raise SystemExit("Run apply_castaway_spare_change_patch.py first: its DOL section 16 holds this code")
    for address in (cw.CAVE_SPIN, cw.CAVE_RANDOM_ORB, wheel.CAVES["spin"][0]):
        at = dol_offset(dol, address)
        if not any(dol[at:at + 16]):
            raise SystemExit(f"Run the Faire/Castaway wheel scripts first: nothing at {address:#x}")
    start = dol_offset(dol, CAVE_SHOW)
    region = bytes(dol[start:start + USED_END - CAVE_SHOW])
    if any(region) and not rel_hooked(rel_data()):
        raise SystemExit(f"{CAVE_SHOW:#x}-{USED_END:#x} is not free (and this script has not run before)")
    for address, code in pieces().items():
        position = dol_offset(dol, address)
        dol[position:position + len(code)] = code
    DOL.write_bytes(dol)
    print(f"E. Gadd's Garage wheel code at {CAVE_SHOW:#x}-{USED_END:#x}")


def patch_rel():
    data = rel_data()
    check_words(data, SITE_PASS, WORD_PASS, "48000001")
    check_words(data, SITE_INIT, "48000001")
    from tools.patches import apply_egadd_robots_patch as robots
    changed = 0
    if robots.site_targets(data, SITE_PASS) != [robots.CAVE_PASS]:
        changed += add_calls(data, [(SITE_PASS, CAVE_PASS)])
    if robots.site_targets(data, SITE_INIT) != [robots.CAVE_INIT]:
        changed += retarget_call(data, SITE_INIT, cw.FN_INIT_TAIL, CAVE_INIT)
    if changed:
        REL_DIR.mkdir(parents=True, exist_ok=True)
        (REL_DIR / REL_NAME).write_bytes(data)
        print(f"Hooked fn_1_39F4 and the board init ({REL_NAME})")
    else:
        print("fn_1_39F4 and the board init already hooked")


def patch_board(board):
    path = GAME_DATA / f"{board}.bin"
    data, offsets = mpdata.read_archive(path)
    blob, start, end = load_spaces(data, offsets)
    at = flag_offset(blob, TRIGGER_SPACE)
    current = struct.unpack_from(">I", blob, at)[0]
    if current == TRIGGER_FLAG:
        print(f"{board}: space {TRIGGER_SPACE} already has flag {TRIGGER_FLAG:#x}")
        return
    if current != 0:
        raise RuntimeError(f"{board}: space {TRIGGER_SPACE} already has flags {current:#x}")
    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = BACKUPS / f"{board}.bin.bak_before_egadd_wheel"
    if not backup.exists():
        shutil.copy2(path, backup)
    struct.pack_into(">I", blob, at, TRIGGER_FLAG)
    packed, _ = replace_file0(data, offsets, start, end, blob)
    path.write_bytes(packed)
    print(f"{board}: space {TRIGGER_SPACE} flag {TRIGGER_FLAG:#x} set")


def patch_messages():
    MESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in MESS_NAMES:
        chained = MESS_OUTPUT_DIR / name
        source = chained if chained.exists() else MESS_SOURCE_DIR / name
        from tools.patches import apply_egadd_robots_patch as robots
        data = source.read_bytes()
        append = RECORDS + robots.RECORDS if robots.bank_count(data) == robots.BANK_RECORDS + len(robots.RECORDS) else RECORDS
        edited = edit_bank(data, {}, name, bank=BANK, bank_records=BANK_RECORDS, append=append, known_tails=())
        (MESS_OUTPUT_DIR / name).write_bytes(edited)
    print(f"Added records {MSG_INTRO}-{MSG_INTRO + len(RECORDS) - 1} to bank {BANK:#x} in {MESS_OUTPUT_DIR}")


def main():
    patch_dol()
    patch_rel()
    for board in BOARDS:
        patch_board(board)
    patch_messages()


if __name__ == "__main__":
    main()
