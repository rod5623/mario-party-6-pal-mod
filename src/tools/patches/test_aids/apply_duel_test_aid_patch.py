"""TEST AID: the Duel space always offers the Daft Rafts and Lift Leapers duel entries.

fn_801F0BCC builds the list of choices (table indices, s16, at r1+0xD8 of its frame) with one of
several pickers, all of which join at 0x801F0F7C (`lis r3, 0x5`, the first instruction after the
list is built; r24 = minigame type, r28 = number of choices). That instruction is replaced by a
`bl` to a cave that, for type 6 and at least two choices, overwrites choices 0 and 1 with table
entries 86 (Daft Rafts duel) and 87 (Lift Leapers duel), then runs the displaced `lis`.

Run after apply_daft_rafts_duel_patch.py and apply_lift_leapers_duel_patch.py.
`python -m tools.patches.test_aids.apply_duel_test_aid_patch --remove` puts the original instruction back.
The cave bytes are left in place (harmless, unreferenced).
"""
import sys

from tools.lib.paths import DOL
from tools.lib.dol import dol_offset, encode_branch
from tools.lib.minigames import NEW_BASE
from tools.lib.ppc import Asm, BLR, STH, i_addi, i_cmpwi, i_lis, i_mem
from tools.lib.dol import write_cave

SITE = 0x801F0F7C
ORIGINAL = bytes.fromhex("3C600005")  # lis r3, 0x5
CAVE = NEW_BASE + 0x3300  # 0x802F7CA0
OUT_ARRAY = 0xD8


def build_cave():
    a = Asm(CAVE)
    a.word(i_cmpwi(24, 6))
    a.branch("bne", "ret")
    a.word(i_cmpwi(28, 2))
    a.branch("blt", "ret")
    a.word(i_addi(12, 0, 86))
    a.word(i_mem(STH, 12, 1, OUT_ARRAY))
    a.word(i_addi(12, 0, 87))
    a.word(i_mem(STH, 12, 1, OUT_ARRAY + 2))
    a.label("ret")
    a.word(i_lis(3, 5))
    a.word(BLR)
    return a.assemble()


def main():
    dol = bytearray(DOL.read_bytes())
    position = dol_offset(dol, SITE)
    current = bytes(dol[position:position + 4])
    hooked = encode_branch(SITE, CAVE, link=True).to_bytes(4, "big") if isinstance(
        encode_branch(SITE, CAVE, link=True), int) else encode_branch(SITE, CAVE, link=True)
    if "--remove" in sys.argv:
        if current == hooked:
            dol[position:position + 4] = ORIGINAL
            print("Test aid removed")
        elif current == ORIGINAL:
            print("Test aid was not installed")
        else:
            raise SystemExit(f"Unexpected word at {SITE:#x}: {current.hex()}")
    else:
        if current not in (ORIGINAL, hooked):
            raise SystemExit(f"Unexpected word at {SITE:#x}: {current.hex()}")
        write_cave(dol, CAVE, build_cave())
        dol[position:position + 4] = hooked
        print("Test aid installed: Duel space offers entries 86 and 87")
    DOL.write_bytes(dol)


if __name__ == "__main__":
    main()
