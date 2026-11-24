"""Count minigames won per player (for the wins-based Mini-game Star).

resultDll's fn_1_37D8 is the only code that pays minigame coins into
GwPlayer+0x1E. It runs in Party mode for every end-of-turn minigame (types 0
4P, 1 1v3, 2 2v2, 3 Battle, 5, 8; Duel/Bowser/DK skip resultDll). At its start
each player's GwPlayer+0x26 (coins picked up) and +0x28 (mgCoinBonus) are still
as the minigame left them, so a call there counts wins into GwPlayer+0x2A
(padding, unused elsewhere; reset at board start by apply_random_bonus_patch.py):

- Battle (type 3): +0x28 holds the place; place 0 (1st, ties included) wins.
  If all four are 0 nobody wins (all tied, or no places written).
- m642 (table index 41) never writes +0x28: anyone with +0x26 > 0 wins.
- Otherwise: anyone with +0x28 > 0 (the winner's 10-coin bonus) wins.
Capped at 99.

Rebuilds resultDll from a pristine asm snapshot (asm_pre_wins/), so it is safe to
re-run, and writes build/GP6P01/files/dll/resultDll.rel. If mgtable_move has
already been applied to the DOL, the REL's minigame-table relocations are
retargeted here too (run before mgtable_move in apply_all.py).
"""
import shutil
import struct
import sys

from tools.lib.paths import DOL
from tools.lib import rebuild_mdpresult

from tools.lib.paths import ROOT
DLL = ROOT / "build/GP6P01/resultDll"
ASM = DLL / "asm"
ASM_PRE = DLL / "asm_pre_wins"
TEXT = ASM / "auto_00_00000000_text.s"
REL_OUT = ROOT / "build/GP6P01/files/dll/resultDll.rel"

M642_INDEX = 41  # MgDataTbl index of m642 (ovl 0x2F, 2v2)

HOOK_OLD = (
    "/* 000037E8 000038C4  48 00 92 E1 */\tbl _savegpr_23\n"
    "/* 000037EC 000038C8  3B A0 00 00 */\tli r29, 0x0\n"
)
HOOK_NEW = (
    "/* 000037E8 000038C4  48 00 92 E1 */\tbl _savegpr_23\n"
    "\tbl fn_1_mgwins\n"
    "/* 000037EC 000038C8  3B A0 00 00 */\tli r29, 0x0\n"
)

# r6 = GwPlayer base, r7 = player, r11 = mode (0 Battle, 1 m642, 2 normal).
NEW_TEXT = f"""
# Minigame wins counter (apply_minigame_wins_patch.py): GwPlayer+0x2A += 1 per win.
.fn fn_1_mgwins, global
	lis r3, lbl_80283290@ha
	addi r3, r3, lbl_80283290@l
	lhz r4, 0x38(r3)
	mulli r0, r4, 0x7c
	lis r3, lbl_8022FF44@ha
	addi r3, r3, lbl_8022FF44@l
	add r3, r3, r0
	lbz r5, 0x2(r3)
	lis r6, lbl_80282E70@ha
	addi r6, r6, lbl_80282E70@l
	li r11, 0x2
	cmplwi r4, {M642_INDEX}
	bne .L_mgw_type
	li r11, 0x1
.L_mgw_type:
	cmplwi r5, 0x3
	bne .L_mgw_start
	li r11, 0x0
	li r7, 0x0
	li r8, 0x0
.L_mgw_bchk:
	mulli r9, r7, 0x108
	add r9, r9, r6
	lha r0, 0x28(r9)
	or r8, r8, r0
	addi r7, r7, 0x1
	cmpwi r7, 0x4
	blt .L_mgw_bchk
	cmpwi r8, 0x0
	beqlr
.L_mgw_start:
	li r7, 0x0
.L_mgw_loop:
	mulli r9, r7, 0x108
	add r9, r9, r6
	cmpwi r11, 0x0
	bne .L_mgw_m1
	lha r0, 0x28(r9)
	cmpwi r0, 0x0
	bne .L_mgw_next
	b .L_mgw_win
.L_mgw_m1:
	cmpwi r11, 0x1
	bne .L_mgw_m2
	lha r0, 0x26(r9)
	cmpwi r0, 0x0
	ble .L_mgw_next
	b .L_mgw_win
.L_mgw_m2:
	lha r0, 0x28(r9)
	cmpwi r0, 0x0
	ble .L_mgw_next
.L_mgw_win:
	lha r0, 0x2a(r9)
	cmpwi r0, 0x63
	bge .L_mgw_next
	addi r0, r0, 0x1
	sth r0, 0x2a(r9)
.L_mgw_next:
	addi r7, r7, 0x1
	cmpwi r7, 0x4
	blt .L_mgw_loop
	blr
.endfn fn_1_mgwins
"""


def dol_has_moved_table():
    """True once apply_mgtable_move_patch.py has added its DOL data section."""
    from tools.lib.minigames import NEW_BASE, SECTION_SLOT
    dol = DOL.read_bytes()
    return struct.unpack_from(">I", dol, 0x48 + 4 * SECTION_SLOT)[0] == NEW_BASE


def patch_asm():
    if not ASM_PRE.exists():
        shutil.copytree(ASM, ASM_PRE)
    for src in ASM_PRE.glob("*.s"):
        shutil.copyfile(src, ASM / src.name)
    text = TEXT.read_text()
    if text.count(HOOK_OLD) != 1:
        raise RuntimeError("fn_1_37D8 hook site not found exactly once")
    text = text.replace(HOOK_OLD, HOOK_NEW, 1)
    TEXT.write_text(text.rstrip("\n") + "\n" + NEW_TEXT)


def main():
    patch_asm()
    rel = rebuild_mdpresult.rebuild("resultDll")
    data = bytearray(rel.read_bytes())
    if dol_has_moved_table():
        from tools.patches.apply_mgtable_move_patch import patch_rel
        print(f"  retargeted {patch_rel(data)} minigame-table relocations")
    REL_OUT.parent.mkdir(parents=True, exist_ok=True)
    REL_OUT.write_bytes(data)
    print(f"Built {REL_OUT}")


if __name__ == "__main__":
    sys.exit(main())
