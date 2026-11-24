"""Castaway Bay: the bridge troll, a green "?" action space (space 39) that only fires when a player STOPS on it.

Space 39 is the last blue space of the bridge between the top cliff and the tower island (route: Boo's house 67,
blue 42, blue 41, then 39; boards/castaway bay/action-space-troll-bridge.png). It becomes kind 3 (green "?") with
flag 0x20000 in w05.bin / w05n.bin. Only kind 3 spaces run the board's landing handler fn_1_20F8, which runs once the
move has ended on the space; walking over 39 runs nothing (the pass handler fn_1_2238 is not hooked for this flag).

Landing on it (human or CPU, no choice) rolls one of four outcomes, equal odds, each line shown first, then applied:
  0 "pay the toll there good lad": 15 coins; with fewer, one Star (game popup); with no Stars, all their coins;
  1 "Those look delish man": every orb the player holds is taken;
  2 "i dont like messers on my bridge": sent back to the start space (fn_80179164(-1, 0x40) = the flag-0x40 space,
    the same lookup the board's raft ride uses; space 92 in the data), the move ends there;
  3 "keep doing what you're doing there pal": nothing.

The "troll" is now a tax man: a flat card that always faces the camera (hsf_build.build_card), the same size as the
spare change guy (TROLL_WIDTH x TROLL_HEIGHT = 130 x 260), at the troll's old position. Art: assets/taxman.png (cut out of
boards/castaway bay/taxman.jpeg: the white background flood-filled from the edges, then cropped; the earlier troll art
was troll-example.jpeg). It is
file 49 of w05.bin / w05n.bin, after the spare change card (48), created at board init.

Hooks (both chained onto earlier Castaway scripts, so run this last):
  * w05Dll .text 0x21BC (exit of fn_1_20F8, r30 = player, r31 = space) calls CAVE_LAND. It tests flag 0x20000 and
    runs the event, then JUMPS (not calls) to the broom's landing cave, so the broom still sees fn_1_20F8's return
    address (it derives the handler's address from it for its Glory destination).
  * w05Dll .text 0x1C2C (the board init's path-mask call) calls CAVE_INIT, which calls the spare change guy's init
    cave first (it makes the original call and creates its card) and then creates the troll's card.

Code: DOL section 16 (added by apply_castaway_spare_change_patch.py), after its caves. Text: bank 0x33 records 69-72
after the spare change guy's 60-68, no speaker face. Run after castaway_spare_change. Idempotent. Not run in Dolphin.
"""
import shutil
import struct

from tools.patches import apply_castaway_broom_patch as broom
from tools.patches import apply_castaway_spare_change_patch as spare
from tools.patches import apply_castaway_wheel_patch as cw
from tools.patches import apply_wheel_of_fortune_patch as wheel
from tools.lib import hsf_build
from tools.lib import mpdata
from tools.lib.paths import DOL
from tools.lib.dol import dol_offset
from tools.lib.game import FN_ADD_COINS, FN_COINS
from tools.lib.paths import MESS_NAMES, MESS_OUTPUT_DIR, MESS_SOURCE_DIR, REL_DIR
from tools.patches.apply_star_shuffle_bet_patch import edit_bank
from tools.lib.ppc import i_li, i_rlwinm
from tools.lib.ppc import Asm, LBZ, LWZ, MTLR, i_addi, i_cmpwi, i_lis, i_mem, i_mr, i_ori, i_slwi, ha, lo
from tools.lib.boards import flag_offset, load_spaces, replace_file0
from tools.lib.game import FN_PLAYER_HOLD, FN_PLAYER_MOTION, FN_RANDOM, FN_STARS
from tools.lib.paths import BACKUPS, GAME_DATA
from tools.lib.ppc import LFS, STB, b_to, epilogue, i_extsh, i_subf, prologue
from tools.lib.rel import check_words

REL_NAME = "w05Dll.rel"
BOARDS = ("w05", "w05n")
from tools.lib.paths import TOOLS
ART = TOOLS / "assets" / "taxman.png"

# the space
SPACE = 39                    # (1981, 716, -694): Boo's house, two blues, then this one
KIND_OLD, KIND_NEW = 1, 3
FLAG = 0x20000                # unused by the board data, w05Dll and the path mask (0x1840); the spare change guy has 0x10000
FLAG_RLWINM = 14              # rlwinm field of bit 0x20000 (mask bit = 31 - field)

# the card
CARD_FILE = spare.CARD_FILE + 1   # 49, after the spare change guy's card
TOTAL_FILES = CARD_FILE + 1
TROLL_WIDTH, TROLL_HEIGHT = 156.0, 312.0   # 20% bigger than the spare change guy (130 x 260)
TROLL_POS = (2020.0, 735.0, -780.0)        # behind space 39 (-694), still on the bridge deck: first guess -650 stood on the space; tune in Dolphin
DIR_DAY, DIR_NIGHT = broom.DIR_DAY, broom.DIR_NIGHT

# outcomes
TOLL = 15
OUTCOMES = 4
START_FLAG = 0x40             # the flag of the start space (fn_80179164 scans for it)
FN_FIND_FLAG = 0x80179164     # (space or -1, flag mask): the first space with a flag in the mask
FN_ORB_REMOVE = 0x8015D8A4    # (player, slot): remove that orb, later ones move up; returns its id, -1 if there is none
MAX_ORBS = 6                  # more than a player can hold: the removal loop's cap

# code: DOL section 16, after the spare change guy's caves
CODE_BASE = spare.CODE_BASE
CAVE_LAND = CODE_BASE + 0x500
CAVE_INIT = CODE_BASE + 0x560
CAVE_EVENT = CODE_BASE + 0x5E0
CAVE_DATA = CODE_BASE + 0xA00
USED_END = CAVE_DATA + 0x10
assert USED_END <= spare.CODE_END

SITE_LAND = broom.SITE_LAND   # 0x21BC
SITE_INIT = spare.SITE_INIT   # 0x1C2C

# text: bank 0x33 after the spare change guy's
BANK = cw.BANK
BANK_RECORDS = spare.BANK_RECORDS + len(spare.RECORDS)  # 69
SPEAKER = spare.SPEAKER

TEXT = [  # the troll's lines, spelled exactly as the user gave them
    spare.say("pay the toll there good lad"),
    spare.say("Those look delish man"),
    spare.say("i dont like messers on my bridge"),
    spare.say("keep doing what you're doing there pal"),
]
MSG_TOLL, MSG_ORBS, MSG_WARP, MSG_NOTHING = range(BANK_RECORDS, BANK_RECORDS + len(TEXT))
RECORDS = TEXT


# ---- code -------------------------------------------------------------------

def build_land(address, broom_land, event):
    """Replaces `li r3,1` at the exit of fn_1_20F8 (r30 = player, r31 = space): the troll on flag FLAG, then the
    broom's cave, jumped to with the caller's return address back in LR so it behaves exactly as before."""
    a = Asm(address)
    frame = 0x10
    prologue(a, frame, ())
    a.word(i_mr(3, 31))
    a.call(spare.FN_FLAGS)
    a.word(i_rlwinm(0, 3, 0, FLAG_RLWINM, FLAG_RLWINM) | 1)
    a.branch("beq", "chain")
    a.word(i_mr(3, 30))
    a.call(CAVE_EVENT)
    a.label("chain")
    a.word(i_mem(LWZ, 0, 1, frame + 4))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, frame))
    a.word(0)                               # b broom_land (patched below)
    code = bytearray(a.assemble())
    struct.pack_into(">I", code, len(code) - 4, b_to(address + len(code) - 4, broom_land))
    return spare.fits(bytes(code), CAVE_INIT - CAVE_LAND, "land")


def build_init(address, spare_init):
    """Replaces the call that the spare change guy's init cave stands at (r3 = 0x1840 is still in place): run that
    cave (the original call and the spare change card), then create the troll's card."""
    a = Asm(address)
    saved = (31,)
    prologue(a, 0x20, saved)
    a.call(spare_init)
    a.word(i_lis(3, ha(spare.GW_SYSTEM)))
    a.word(i_addi(3, 3, lo(spare.GW_SYSTEM)))
    a.word(i_mem(LBZ, 0, 3, 0x10))
    a.word(i_rlwinm(0, 0, 0, 25, 25) | 1)  # night bit 0x40
    a.word(i_li(3, DIR_DAY))
    a.branch("beq", "day")
    a.word(i_li(3, DIR_NIGHT))
    a.label("day")
    a.word(i_slwi(3, 3, 16))
    a.word(i_ori(3, 3, CARD_FILE))
    a.word(i_li(4, 0))
    a.word(i_li(5, 0))
    a.call(spare.FN_OBJ_CREATE)
    a.word(i_extsh(31, 3))
    a.word(i_mr(3, 31))
    a.word(i_li(4, 3))
    a.call(spare.FN_OBJ_LAYER)
    a.word(i_mr(3, 31))
    a.word(i_lis(4, ha(CAVE_DATA)))
    a.word(i_addi(4, 4, lo(CAVE_DATA)))
    a.call(spare.FN_OBJ_POS)
    epilogue(a, 0x20, saved)
    return spare.fits(a.assemble(), CAVE_EVENT - CAVE_INIT, "init")


def build_event(address, show):
    """r3 = player: hold them, roll, show the line, apply it, release them."""
    a = Asm(address)
    saved = (28, 29, 30, 31)
    frame = 0x30
    prologue(a, frame, saved)
    a.word(i_mr(31, 3))
    # hold the player and stop the walk animation, as the spare change guy does
    a.word(i_mr(3, 31))
    a.word(i_li(4, 0))
    a.call(FN_PLAYER_HOLD)
    a.word(i_mr(3, 31))
    a.word(i_li(4, 1))
    a.word(i_lis(5, ha(spare.CAVE_DATA)))
    a.word(i_mem(LFS, 1, 5, lo(spare.CAVE_DATA + spare.D_ZERO)))
    a.word(i_mem(LFS, 2, 5, lo(spare.CAVE_DATA + spare.D_EIGHT)))
    a.word(i_lis(5, 0x4000))
    a.word(i_addi(5, 5, 1))
    a.call(FN_PLAYER_MOTION)
    a.word(i_li(3, OUTCOMES))
    a.call(FN_RANDOM)
    a.word(i_mr(30, 3))
    # 0: the toll
    a.word(i_cmpwi(30, 0))
    a.branch("bne", "orbs")
    a.word(i_li(3, MSG_TOLL))
    a.call(show)
    a.word(i_mr(3, 31))
    a.call(FN_COINS)
    a.word(i_mr(29, 3))
    a.word(i_cmpwi(29, TOLL))
    a.branch("blt", "poor")
    a.word(i_mr(3, 31))
    a.word(i_li(4, -TOLL))
    a.word(i_li(5, 1))
    a.word(i_li(6, 1))
    a.call(FN_ADD_COINS)
    a.branch("b", "done")
    a.label("poor")  # cannot pay: a Star instead
    a.word(i_mr(3, 31))
    a.call(FN_STARS)
    a.word(i_cmpwi(3, 0))
    a.branch("ble", "broke")
    a.word(i_mr(3, 31))
    a.word(i_li(4, -1))
    a.call(wheel.CAVES["stars"][0])  # Star change with the game's popup, waits for it
    a.branch("b", "done")
    a.label("broke")  # no Star either: every coin they have
    a.word(i_cmpwi(29, 0))
    a.branch("ble", "done")
    a.word(i_mr(3, 31))
    a.word(i_li(4, 0))
    a.word(i_subf(4, 29, 4))  # r4 = -r29
    a.word(i_li(5, 1))
    a.word(i_li(6, 1))
    a.call(FN_ADD_COINS)
    a.branch("b", "done")
    # 1: every orb
    a.label("orbs")
    a.word(i_cmpwi(30, 1))
    a.branch("bne", "warp")
    a.word(i_li(3, MSG_ORBS))
    a.call(show)
    a.word(i_li(29, 0))
    a.label("take")
    a.word(i_mr(3, 31))
    a.word(i_li(4, 0))  # slot 0: the rest move up
    a.call(FN_ORB_REMOVE)
    a.word(i_cmpwi(3, -1))
    a.branch("beq", "done")
    a.word(i_addi(29, 29, 1))
    a.word(i_cmpwi(29, MAX_ORBS))
    a.branch("blt", "take")
    a.branch("b", "done")
    # 2: back to the start space
    a.label("warp")
    a.word(i_cmpwi(30, 2))
    a.branch("bne", "nothing")
    a.word(i_li(3, MSG_WARP))
    a.call(show)
    a.word(i_li(3, -1))
    a.word(i_li(4, START_FLAG))
    a.call(FN_FIND_FLAG)
    a.word(i_extsh(29, 3))
    a.word(i_cmpwi(29, 1))
    a.branch("blt", "done")  # no start space found: stay
    a.word(i_li(3, cw.SOUND_TELEPORT))
    a.call(cw.FN_SOUND)
    a.word(i_mr(3, 29))
    a.word(i_addi(4, 1, 0x10))
    a.call(cw.FN_SPACE_POS)
    a.word(i_mr(3, 31))
    a.word(i_addi(4, 1, 0x10))
    a.call(cw.FN_PLAYER_POS)
    spare.gw_player(a, 5, 31)
    a.word(i_mem(wheel.STH, 29, 5, 0xC))  # GwPlayer.masuId = the start space
    a.word(i_li(0, 0))
    a.word(i_mem(STB, 0, 5, 0xA))   # no steps left: the move ends there
    a.word(i_li(3, 20))
    a.call(cw.FN_WAIT)
    a.branch("b", "done")
    # 3: nothing
    a.label("nothing")
    a.word(i_li(3, MSG_NOTHING))
    a.call(show)
    a.label("done")
    a.word(i_mr(3, 31))
    a.word(i_li(4, 1))
    a.call(FN_PLAYER_HOLD)
    epilogue(a, frame, saved)
    return spare.fits(a.assemble(), CAVE_DATA - CAVE_EVENT, "event")


def build_data():
    return struct.pack(">3f", *TROLL_POS) + b"\0" * 4


def pieces(broom_land, spare_init):
    return {
        CAVE_LAND: build_land(CAVE_LAND, broom_land, CAVE_EVENT),
        CAVE_INIT: build_init(CAVE_INIT, spare_init),
        CAVE_EVENT: build_event(CAVE_EVENT, spare.CAVE_SHOW),
        CAVE_DATA: build_data(),
    }


# ---- DOL --------------------------------------------------------------------

def patch_dol():
    dol = bytearray(DOL.read_bytes())
    tag = struct.unpack_from(">I", dol, 0x48 + 4 * spare.SECTION)[0]
    if tag != spare.CODE_BASE:
        raise SystemExit("Run apply_castaway_spare_change_patch.py first: its DOL section 16 holds the troll's code")
    for address, code in pieces(broom.CAVE_LAND, spare.CAVE_INIT).items():
        position = dol_offset(dol, address)
        dol[position:position + len(code)] = code
    DOL.write_bytes(dol)
    print(f"Troll code at {CAVE_LAND:#x}-{USED_END:#x} (event {len(pieces(broom.CAVE_LAND, spare.CAVE_INIT)[CAVE_EVENT]):#x} bytes)")


# ---- REL --------------------------------------------------------------------

def patch_rel():
    path = REL_DIR / REL_NAME
    if not path.exists():
        raise SystemExit("Run the Castaway wheel, broom and spare change scripts first")
    data = bytearray(path.read_bytes())
    check_words(data, SITE_LAND, "48000001")
    check_words(data, SITE_INIT, "48000001")
    changed = broom.point_call(data, SITE_LAND, CAVE_LAND, (broom.CAVE_LAND,), earlier=(broom.CAVE_LAND,))
    changed += broom.point_call(data, SITE_INIT, CAVE_INIT, (spare.CAVE_INIT,), earlier=(spare.CAVE_INIT,))
    if changed:
        path.write_bytes(data)
        print(f"Hooked the landing handler (troll, then broom) and the board init ({REL_NAME})")
    else:
        print("Landing handler and board init already hooked")


# ---- board data -------------------------------------------------------------

def card_image():
    from PIL import Image
    if not ART.exists():
        raise SystemExit(f"{ART} is missing (cut the tax man out of boards/castaway bay/taxman.jpeg)")
    art = Image.open(ART).convert("RGBA")
    art.thumbnail((spare.CARD_W, spare.CARD_H), Image.LANCZOS)
    image = Image.new("RGBA", (spare.CARD_W, spare.CARD_H), (0, 0, 0, 0))
    image.paste(art, ((spare.CARD_W - art.width) // 2, spare.CARD_H - art.height))  # feet on the bottom edge
    return image


def card_model():
    blob = hsf_build.build_card(card_image(), TROLL_WIDTH, TROLL_HEIGHT, name="taxman")
    hsf_build.check(blob)
    return blob


def patch_board(board, model):
    path = GAME_DATA / f"{board}.bin"
    data, offsets = mpdata.read_archive(path)
    if len(offsets) not in (CARD_FILE, TOTAL_FILES):
        raise SystemExit(f"{board}: {len(offsets)} files: run apply_castaway_spare_change_patch.py first (expected {CARD_FILE})")
    blob, start, end = load_spaces(data, offsets)
    at = flag_offset(blob, SPACE)
    flags, kind = struct.unpack_from(">I", blob, at)[0], struct.unpack_from(">H", blob, at + 4)[0]
    space_done = (flags, kind) == (FLAG, KIND_NEW)
    if not space_done and (flags, kind) != (0, KIND_OLD):
        raise RuntimeError(f"{board}: space {SPACE} has flags {flags:#x}, kind {kind} (expected 0, {KIND_OLD})")
    current = mpdata.read_file(data, offsets, CARD_FILE) if len(offsets) == TOTAL_FILES else None
    if space_done and current == model:
        print(f"{board}: space {SPACE} and the troll card (file {CARD_FILE}) already in place")
        return
    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = BACKUPS / f"{board}.bin.bak_before_troll"
    if not backup.exists():
        shutil.copy2(path, backup)
    if not space_done:
        struct.pack_into(">I", blob, at, FLAG)
        struct.pack_into(">H", blob, at + 4, KIND_NEW)
        data, offsets = replace_file0(data, offsets, start, end, blob)
    if current != model:
        if current is not None:  # new art: replace the card
            data, offsets = wheel.drop_last_file(data, offsets)
        data, offsets = mpdata.append_files(data, offsets, [model])
    path.write_bytes(data)
    print(f"{board}: space {SPACE} is the troll's \"?\" space (flag {FLAG:#x}); card is file {CARD_FILE}")


# ---- text -------------------------------------------------------------------

def patch_messages():
    MESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in MESS_NAMES:
        chained = MESS_OUTPUT_DIR / name
        source = chained if chained.exists() else MESS_SOURCE_DIR / name
        edited = edit_bank(source.read_bytes(), {}, name, bank=BANK, bank_records=BANK_RECORDS, append=RECORDS, known_tails=())
        (MESS_OUTPUT_DIR / name).write_bytes(edited)
    print(f"Added records {MSG_TOLL}-{MSG_NOTHING} to bank {BANK:#x}")


def main():
    patch_dol()
    patch_rel()
    model = card_model()
    print(f"Card texture: {ART}")
    for board in BOARDS:
        patch_board(board, model)
    patch_messages()


if __name__ == "__main__":
    main()
