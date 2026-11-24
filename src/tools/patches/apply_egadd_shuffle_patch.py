"""E. Gadd's Garage: Shuffle-o-tron (day event on spaces 36/38, w02Dll fn_1_B11C) gives a bonus orb.

Vanilla: with n > 0 orbs the player (CPUs always) can shuffle: the machine takes all n orbs (fn_1_B570 mode 2) and
gives back n random ones from the board's orb list (mode 3, count in r5). With 0 orbs E. Gadd just says "No Orbs,
eh?" (message 0x300008).

Now it gives back n + 1 while n < 3, otherwise n (0 -> 1, 1 -> 2, 2 -> 3, 3 -> 3; in team mode, max 5, counts of
3 and more stay as they are, so the result never exceeds the pocket limit):
  * .text 0xB168 `bgt .L_B1A0` (only with orbs) -> `b .L_B1A0`: the offer is shown with 0 orbs too. Mode 2 then
    takes nothing (its loop runs 0 times) and the machine animation plays as usual.
  * .text 0xB2AC `mr r5,r28` (r28 = orbs held on arrival) -> module-0 call to a 5-word DOL leaf at 0x802F8D80
    (cmpwi r28,3 / addi r5,r28,1 / bltlr / mr r5,r28 / blr); r3/r4 are untouched.
Message 0x300008 ("No Orbs, eh?") is no longer used. The Orb Morpher (night) is unchanged.

Run after apply_egadd_calamity_patch.py (chained w02Dll.rel; DOL section 16 after its cave). Idempotent.
Not run in Dolphin.
"""
import struct

from tools.patches import apply_castaway_spare_change_patch as spare
from tools.patches import apply_egadd_calamity_patch as cal
from tools.lib.paths import DOL
from tools.lib.dol import dol_offset
from tools.lib.paths import REL_DIR
from tools.lib.rel import add_calls, check_words, text_base

REL_NAME = cal.REL_NAME
SITE_GATE = 0xB168
GATE_OLD, GATE_NEW = "41810038", 0x48000038      # bgt .L_B1A0 -> b .L_B1A0
SITE_COUNT = 0xB2AC
COUNT_OLD = "7F85E378"                            # mr r5, r28
CAVE_COUNT = 0x802F8D80
CAVE_END = CAVE_COUNT + 0x14
assert cal.CAVE_END <= CAVE_COUNT and CAVE_END <= spare.CODE_END
MAX_BONUS = 3                                     # below this many orbs, one extra


def build_cave():
    return struct.pack(">5I",
                       0x2C1C0000 | MAX_BONUS,    # cmpwi r28, 3
                       0x38BC0001,                # addi r5, r28, 1
                       0x4D800020,                # bltlr
                       0x7F85E378,                # mr r5, r28
                       0x4E800020)                # blr


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    if struct.unpack_from(">I", dol, 0x48 + 4 * spare.SECTION)[0] != spare.CODE_BASE:
        raise SystemExit("Run apply_castaway_spare_change_patch.py first: its DOL section 16 holds this code")
    code = build_cave()
    at = dol_offset(dol, CAVE_COUNT)
    if dol[at:at + len(code)] not in (bytes(len(code)), code):
        raise SystemExit(f"{CAVE_COUNT:#x} is not free")
    dol[at:at + len(code)] = code
    DOL.write_bytes(dol)
    print(f"Shuffle-o-tron count routine at {CAVE_COUNT:#x}")


def patch_rel():
    path = REL_DIR / REL_NAME
    if not path.exists():
        raise SystemExit("Run apply_egadd_wheel_patch.py and apply_egadd_calamity_patch.py first")
    data = bytearray(path.read_bytes())
    text = text_base(data)
    check_words(data, SITE_GATE, GATE_OLD, f"{GATE_NEW:08X}")
    struct.pack_into(">I", data, text + SITE_GATE, GATE_NEW)
    check_words(data, SITE_COUNT, COUNT_OLD, "48000001")
    add_calls(data, [(SITE_COUNT, CAVE_COUNT)])
    path.write_bytes(data)
    print(f"Shuffle-o-tron: offer with 0 orbs, bonus orb count ({REL_NAME})")


def main():
    patch_dol()
    patch_rel()


if __name__ == "__main__":
    main()
