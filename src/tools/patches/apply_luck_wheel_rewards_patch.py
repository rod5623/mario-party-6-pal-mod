"""Faire Square Luck Wheel (the 3-reel slot machine, fn_1_2718): extra rewards when all three reels match.

The normal prize (coins, grand prize pot) is paid exactly as before. After the coin pickup, and before
the closing "Come again soon" line, the matched symbol adds:
  id 0  chest      +1 Star (popup) and +1 orb
  id 1  mushroom   +20 coins and +1 orb
  id 2  flower     +1 Star (popup)
  id 3  coin       +1 orb
Orbs are only given while the player holds fewer than the maximum (3); the orb is a random Super
'Shroom / Sluggish / Flutter, as in the Wheel of Fortune's Item Windfall.

Hook: w03Dll .text 0x5520, `li r3,1` right before `bl fn_1_12A54` for the closing line. Only the match
path reaches it (a mismatch branches away at 0x4E68/0x4E7C). r30 = player, the three reel symbols are the
halfwords at 0xA8(r1) (reel 0), 0xAA, 0xAC of fn_1_2718's frame; they are all equal on a match. The hook is a
module-0 call to the cave below, which runs the rewards, then the displaced `li r3,1`.

Code space: the old MgDataTbl just after the Wheel of Fortune's code (0x80230690...); its rows are dead
once apply_mgtable_move_patch.py has relocated the table. The Star popup
routine is the Wheel of Fortune's own cave, so run this after apply_wheel_of_fortune_patch.py.
Idempotent. Nothing here has been run in Dolphin.
"""
import struct

from tools.lib.paths import DOL
from tools.lib.dol import dol_offset
from tools.lib.ppc import Asm, BLR, LWZ, MFLR, MTLR, STW, STWU, i_addi, i_cmpw, i_cmpwi, i_mem, i_mr
from tools.lib.minigames import NEW_BASE, SECTION_SLOT
from tools.lib.paths import REL_DIR, REL_ORIG
from tools.patches.apply_star_shuffle_bet_patch import REL_NAME
from tools.lib.ppc import i_li
from tools.patches import apply_wheel_of_fortune_patch as wheel
from tools.lib.game import FN_ORB_ADD, FN_ORB_COUNT, FN_ORB_MAX, FN_RANDOM
from tools.lib.rel import add_calls, check_words

LHA = 42

CAVE_REWARDS = 0x80230690
CAVE_ORB = 0x80230720
CAVE_END = 0x80230790          # still the dead old MgDataTbl rows (the table was relocated to NEW_BASE)
CAVE_STARS = wheel.CAVES["stars"][0]   # (player, delta): Stars with popup

SITE_HOOK = 0x5520             # w03Dll .text: li r3,1 before the closing line of the Luck Wheel
WORD_HOOK = "38600001"

SYMBOL_CHEST, SYMBOL_MUSHROOM, SYMBOL_FLOWER, SYMBOL_COIN = 0, 1, 2, 3
SYMBOL_SLOT = 0xA8             # offset of reel 0's symbol in fn_1_2718's frame
FRAME = 0x30
EXTRA_COINS = 20

FN_ADD_COINS = 0x8017E03C      # (player, amount, 1, 1)


def build_rewards(address):
    """Called at the Luck Wheel hook (r30 = player). Stars, then an orb, then coins, by matched symbol."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -FRAME))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, FRAME + 4))
    a.word(i_mem(STW, 31, 1, FRAME - 4))
    a.word(i_mem(LHA, 31, 1, FRAME + SYMBOL_SLOT))

    a.word(i_cmpwi(31, SYMBOL_CHEST))
    a.branch("beq", "star")
    a.word(i_cmpwi(31, SYMBOL_FLOWER))
    a.branch("bne", "no_star")
    a.label("star")
    a.word(i_mr(3, 30))
    a.word(i_li(4, 1))
    a.call(CAVE_STARS)
    a.label("no_star")

    a.word(i_cmpwi(31, SYMBOL_FLOWER))
    a.branch("beq", "no_orb")
    a.word(i_cmpwi(31, SYMBOL_COIN))
    a.branch("bgt", "no_orb")
    a.word(i_mr(3, 30))
    a.call(CAVE_ORB)
    a.label("no_orb")

    a.word(i_cmpwi(31, SYMBOL_MUSHROOM))
    a.branch("bne", "done")
    a.word(i_mr(3, 30))
    a.word(i_li(4, EXTRA_COINS))
    a.word(i_li(5, 1))
    a.word(i_li(6, 1))
    a.call(FN_ADD_COINS)

    a.label("done")
    a.word(i_li(3, 1))  # the displaced instruction
    a.word(i_mem(LWZ, 0, 1, FRAME + 4))
    a.word(i_mem(LWZ, 31, 1, FRAME - 4))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, FRAME))
    a.word(BLR)
    return a.assemble()


def build_one_orb(address):
    """r3 = player: if there is a free orb slot, add one random Super 'Shroom (1), Sluggish (2) or Flutter (6)."""
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 31, 1, 0x1C))
    a.word(i_mem(STW, 30, 1, 0x18))
    a.word(i_mr(31, 3))
    a.call(FN_ORB_MAX)
    a.word(i_mr(30, 3))
    a.word(i_mr(3, 31))
    a.call(FN_ORB_COUNT)
    a.word(i_cmpw(3, 30))
    a.branch("bge", "end")  # already full
    a.word(i_li(3, 3))
    a.call(FN_RANDOM)
    a.word(i_cmpwi(3, 2))
    a.branch("bne", "pick")
    a.word(i_li(3, 5))
    a.label("pick")
    a.word(i_addi(4, 3, 1))  # 0 -> 1, 1 -> 2, 5 -> 6
    a.word(i_mr(3, 31))
    a.call(FN_ORB_ADD)
    a.label("end")
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(i_mem(LWZ, 31, 1, 0x1C))
    a.word(i_mem(LWZ, 30, 1, 0x18))
    a.word(MTLR(0))
    a.word(i_addi(1, 1, 0x20))
    a.word(BLR)
    return a.assemble()


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    section = struct.unpack_from(">I", dol, 0x48 + 4 * SECTION_SLOT)[0]
    if section != NEW_BASE:
        raise SystemExit("Run apply_mgtable_move_patch.py first")
    stars = wheel.build_stars(CAVE_STARS)
    position = dol_offset(dol, CAVE_STARS)
    if bytes(dol[position:position + len(stars)]) != stars:
        raise SystemExit("Run apply_wheel_of_fortune_patch.py first: its Star routine is not at the expected address")
    code = {CAVE_REWARDS: build_rewards(CAVE_REWARDS), CAVE_ORB: build_one_orb(CAVE_ORB)}
    if len(code[CAVE_REWARDS]) > CAVE_ORB - CAVE_REWARDS or len(code[CAVE_ORB]) > CAVE_END - CAVE_ORB:
        raise RuntimeError("Luck Wheel cave code is too big")
    start = dol_offset(dol, CAVE_REWARDS)
    region = bytes(dol[start:dol_offset(dol, CAVE_END)])
    expected = bytearray(len(region))
    for address, blob in code.items():
        expected[address - CAVE_REWARDS:address - CAVE_REWARDS + len(blob)] = blob
    if region != bytes(expected):
        dol[start:start + len(region)] = expected
        DOL.write_bytes(dol)
        print("Luck Wheel reward code written at", hex(CAVE_REWARDS), "and", hex(CAVE_ORB))
    else:
        print("Luck Wheel reward code already in the DOL")


def patch_rel():
    path = REL_DIR / REL_NAME
    data = bytearray((path if path.exists() else REL_ORIG / REL_NAME).read_bytes())
    check_words(data, SITE_HOOK, WORD_HOOK, "48000001")
    if add_calls(data, [(SITE_HOOK, CAVE_REWARDS)]):
        REL_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"Hooked the Luck Wheel payout ({REL_NAME} .text {SITE_HOOK:#x})")
    else:
        print("Luck Wheel already hooked")


def main():
    patch_dol()
    patch_rel()


if __name__ == "__main__":
    main()
