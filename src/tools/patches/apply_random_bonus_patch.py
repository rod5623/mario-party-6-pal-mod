"""Random bonus stars: draw 3 of the award pool at the end of a Party game.

Pool (award ids): 0 Mini-game (minigames WON: GwPlayer+0x2A, counted by
apply_minigame_wins_patch.py, reset here at 0x8014C00C), 1 Orb,
7 Unlucky (coins + 30 x Stars lost: GwPlayer+0x104, counted by
apply_unlucky_patch.py, reset here in the board-init cave), 3 Coin (revived cut content),
4 Heart (? + Duel + Miracle + Bowser + DK spaces, summed), 5 Distance (FEWEST
spaces moved), 6 Trap Merchant (orbs landed on, plus trap orbs passed over).
Award 2 (vanilla Action Star) is folded into the Heart Star and never drawn.

Always rebuilds from pristine copies, so it is safe to re-run:
- build/GP6P01/mdpresultdll/asm_pre_random/*.s  -> mdpresultdll asm listings
- orig/GP6P01/files/mess/messdata_eng.bin -> bank 0x0E, spliced into the current
  build English messages (other patches' banks are kept)
- build/GP6P01/main.dol: the DOL step counter is patched in place (idempotent).
Then reassembles/relinks the REL and copies REL, messages and DOL into root/.

How it works
- fn_1_17BF8 calls fn_1_bonus_run instead of fn_1_1245C(0/1/2). That draws 3
  distinct ids (partial Fisher-Yates over frandmod) and runs fn_1_1245C for each.
- fn_1_1245C keeps its 3-column message table. Ids >= 3 are remapped to column 0
  of their own table, and the real id is kept in lbl_1_bss_14E4 for fn_1_122F0.
  Each award has a "first" and a "plain" table, because the first award of the
  ceremony carries the Bonus Star opening text.
- fn_1_122F0 reads the stat from a per-award offset table (lbl_1_rodata_FF8),
  plus up to four extra offsets that are added (lbl_1_rodata_stat_extra, used
  by the Heart Star). Offset 0xFF means "distance": read
  lbl_1_bss_14EC[entry], which fn_1_56C fills from GwPlayer+0x106, and
  inverted to 0x7FFF - steps so highest-stat-wins picks the fewest steps.
- DOL: GwPlayer+0x106 (padding) counts steps. It is incremented where moveNum
  is decremented (0x80154BE8, 0x801A0808) and cleared in the board init
  (0x8014C024).
"""
import shutil
import struct
import sys

from tools.lib.paths import DOL, MESS_OUTPUT, MESS_SOURCE
from tools.lib.dol import dol_offset, encode_branch
from tools.lib.messages import write_bank

from tools.lib.paths import ROOT
DLL = ROOT / "build/GP6P01/mdpresultdll"
ASM = DLL / "asm"
ASM_PRE = DLL / "asm_pre_random"
TEXT = ASM / "auto_00_00000000_text.s"
RODATA = ASM / "auto_03_00000000_rodata.s"
BSS = ASM / "auto_05_00000000_bss.s"
GAME_ROOT = ROOT.parent / "root"

BANK = 0x0E
ORIGINAL_COUNT = 66
# Award ids the ceremony draws 3 of. Award 2 (Action) is folded into Heart (4).
DRAW_IDS = [0, 1, 3, 4, 5, 6, 7]
POOL = len(DRAW_IDS)

# Entry offsets (results-table entry) of each award's stat. 0xFF = distance array.
# 0xFE = Unlucky array (lbl_1_bss_unl, from GwPlayer+0x104).
STAT_OFFSETS = [0x0A, 0x0C, 0x0E, 0x08, 0x0E, 0xFF, 0x1C, 0xFE]
# Up to four extra entry offsets added to the stat (0 = end of list).
# Heart: ? spaces (0x0E above) + Duel 0x20 + Miracle 0x22 + Bowser 0x24 + DK 0x26.
STAT_EXTRA = [[0] * 4 for _ in range(8)]
STAT_EXTRA[4] = [0x20, 0x22, 0x24, 0x26]

# Colour codes (1E nn): 2 blue-ish, 3 red, 5, 6, 7 are used by vanilla text.
COIN_COLOR = 0x01
HEART_COLOR = 3
DIST_COLOR = 2
MAGNET_COLOR = 3
UNLUCKY_COLOR = 5

# Original 3-column message table (lbl_1_rodata_4A8), rows 0-9 party, 10-15 tag.
ORIG_TABLE = [
    (0x05, 0x37, 0x13), (0x06, 0x06, 0x06), (0x07, 0x38, 0x14),
    (0x08, 0x08, 0x08), (0x09, 0x39, 0x15), (0x0A, 0x0A, 0x0A),
    (0x0B, 0x0B, 0x0B), (0x0C, 0x0D, 0x0C), (0x0E, 0x3A, 0x16),
    (0x0C, 0x0D, 0x0C), (0x1D, 0x3B, 0x25), (0x1E, 0x1E, 0x1E),
    (0x1F, 0x1F, 0x1F), (0x20, 0x21, 0x20), (0x22, 0x3C, 0x26),
    (0x20, 0x21, 0x20),
]

# New record ids (appended to bank 0x0E): 9 for the vanilla awards + Coin, then
# 8 for Heart, then 12 each for Distance and Trap Merchant.
NEXT = ORIGINAL_COUNT
P_MG_PLAIN, P_ORB_FIRST, P_ACT_FIRST, P_COIN_FIRST = range(NEXT, NEXT + 4)
T_MG_PLAIN, T_ORB_FIRST, T_ACT_PLAIN, T_ACT_FIRST, T_COIN_FIRST = range(NEXT + 4, NEXT + 9)
HEART_BASE = NEXT + 9     # plain intro, first intro, two, three, none, t plain, t first, t none
DIST_BASE = HEART_BASE + 8
MAGNET_BASE = DIST_BASE + 12
# Mini-game Star (wins): tag first intro, then party 1/2/3-winner and tag name pages.
T_MG_FIRST, MG_N1, MG_N2, MG_N3, MG_TN = range(MAGNET_BASE + 12, MAGNET_BASE + 17)
UNLUCKY_BASE = MG_TN + 1
NEW_COUNT = 9 + 8 + 12 + 12 + 5 + 12


def msg(index):
    return 0x000E0000 | index


def award_rows(p_intro, p_two, p_three, p_none, t_intro, t_none,
               n1=0x06, n2=0x08, n3=0x0A, tn=0x1E):
    """Column-0 rows for an award, party rows 0-9 then tag rows 10-15."""
    return [p_intro, n1, p_two, n2, p_three, n3, 0x0B, 0x0C, p_none, 0x0C,
            t_intro, tn, 0x1F, 0x20, t_none, 0x20]


def main_table(first):
    rows = [list(r) for r in ORIG_TABLE]
    if first:
        rows[0] = [0x05, P_ORB_FIRST, P_ACT_FIRST]
        rows[10] = [T_MG_FIRST, T_ORB_FIRST, T_ACT_FIRST]
    else:
        rows[0] = [P_MG_PLAIN, 0x37, 0x13]
        rows[10] = [T_MG_PLAIN, 0x3B, T_ACT_PLAIN]
    # Mini-game column: winner pages that also show the number of wins.
    for row, name in ((1, MG_N1), (3, MG_N2), (5, MG_N3), (11, MG_TN)):
        rows[row][0] = name
    return [[msg(w) for w in r] for r in rows]


def single_table(rows):
    return [[msg(w)] * 3 for w in rows]


def tables():
    coin = award_rows(0x0F, 0x10, 0x11, 0x12, 0x23, 0x24)
    heart = award_rows(HEART_BASE, HEART_BASE + 2, HEART_BASE + 3, HEART_BASE + 4,
                       HEART_BASE + 5, HEART_BASE + 7)
    dist = award_rows(DIST_BASE, DIST_BASE + 2, DIST_BASE + 3, DIST_BASE + 4,
                      DIST_BASE + 5, DIST_BASE + 7, DIST_BASE + 8, DIST_BASE + 9,
                      DIST_BASE + 10, DIST_BASE + 11)
    magnet = award_rows(MAGNET_BASE, MAGNET_BASE + 2, MAGNET_BASE + 3, MAGNET_BASE + 4,
                        MAGNET_BASE + 5, MAGNET_BASE + 7, MAGNET_BASE + 8, MAGNET_BASE + 9,
                        MAGNET_BASE + 10, MAGNET_BASE + 11)
    unlucky = award_rows(UNLUCKY_BASE, UNLUCKY_BASE + 2, UNLUCKY_BASE + 3, UNLUCKY_BASE + 4,
                         UNLUCKY_BASE + 5, UNLUCKY_BASE + 7, UNLUCKY_BASE + 8, UNLUCKY_BASE + 9,
                         UNLUCKY_BASE + 10, UNLUCKY_BASE + 11)
    out = [main_table(False), main_table(True)]
    for rows, p_first, t_first in (
        (coin, P_COIN_FIRST, T_COIN_FIRST),
        (heart, HEART_BASE + 1, HEART_BASE + 6),
        (dist, DIST_BASE + 1, DIST_BASE + 6),
        (magnet, MAGNET_BASE + 1, MAGNET_BASE + 6),
        (unlucky, UNLUCKY_BASE + 1, UNLUCKY_BASE + 6),
    ):
        out.append(single_table(rows))
        first = list(rows)
        first[0], first[10] = p_first, t_first
        out.append(single_table(first))
    return out


def table_asm(rows):
    return "".join(f"\t.4byte 0x{w:08X}\n" for r in rows for w in r)


def byte_line(values):
    return "\t.byte " + ", ".join(f"0x{b:02X}" for b in values) + "\n"


def rodata_block():
    out = "\n# .rodata:0xFF8 | 0xFF8 | size: 0x10\n.obj lbl_1_rodata_FF8, global\n"
    # The second row is unused (it held the old Boss Star's second offset); kept
    # so the message tables after it stay where they were.
    out += byte_line(STAT_OFFSETS) + byte_line([0] * 8)
    out += ".endobj lbl_1_rodata_FF8\n"
    sets = tables()
    out += f"\n# .rodata:0x1008 | 0x1008 | size: 0x{0xC0 * len(sets):X}\n.obj lbl_1_rodata_1008, global\n"
    out += "".join(table_asm(t) for t in sets)
    out += ".endobj lbl_1_rodata_1008\n"
    out += "\n.obj lbl_1_rodata_stat_extra, global\n"
    out += "".join(byte_line(row) for row in STAT_EXTRA)
    out += ".endobj lbl_1_rodata_stat_extra\n"
    return out


BSS_BLOCK = """
# .bss:0x14E4 | 0x14E4 | size: 0x8
.obj lbl_1_bss_14E4, global
	.skip 0x8
.endobj lbl_1_bss_14E4

# .bss:0x14EC | 0x14EC | size: 0x8
.obj lbl_1_bss_14EC, global
	.skip 0x8
.endobj lbl_1_bss_14EC

# .bss:0x14F4 | 0x14F4 | size: 0x10
.obj lbl_1_bss_14F4, global
	.skip 0x10
.endobj lbl_1_bss_14F4

.obj lbl_1_bss_unl, global
	.skip 0x8
.endobj lbl_1_bss_unl
"""

# Fills the stack pool (0x8(r1)...) with the drawable award ids.
DRAW_FILL = "".join(f"\tli r0, 0x{a:X}\n\tstb r0, 0x{8 + i:X}(r1)\n" for i, a in enumerate(DRAW_IDS))

NEW_TEXT = f"""
# Random bonus star driver and fn_1_1245C hooks (apply_random_bonus_patch.py)
.fn fn_1_bonus_run, global
	stwu r1, -0x20(r1)
	mflr r0
	stw r0, 0x24(r1)
	stw r31, 0x1c(r1)
{DRAW_FILL}	li r31, 0x0
.L_bonus_shuffle:
	subfic r3, r31, {POOL}
	bl fn_8003FD50
	add r3, r3, r31
	addi r4, r1, 0x8
	lbzx r5, r4, r31
	lbzx r6, r4, r3
	stbx r6, r4, r31
	stbx r5, r4, r3
	addi r31, r31, 0x1
	cmpwi r31, 0x3
	blt .L_bonus_shuffle
	li r31, 0x0
.L_bonus_award:
	cntlzw r0, r31
	srwi r0, r0, 5
	lis r4, lbl_1_bss_14E4@ha
	addi r4, r4, lbl_1_bss_14E4@l
	sth r0, 0x2(r4)
	addi r4, r1, 0x8
	lbzx r3, r4, r31
	bl fn_1_1245C
	addi r31, r31, 0x1
	cmpwi r31, 0x3
	blt .L_bonus_award
	lwz r0, 0x24(r1)
	lwz r31, 0x1c(r1)
	mtlr r0
	addi r1, r1, 0x20
	blr
.endfn fn_1_bonus_run

# Insert the winners' stat as text insert slot 5 ("1F 05") for the Mini-game (0,
# wins), Distance (5, fewest steps), Trap Merchant (6) and Unlucky (7) Stars.
# r3 = winner count.
.fn fn_1_dist_ins, global
	stwu r1, -0x10(r1)
	mflr r0
	stw r0, 0x14(r1)
	mr r12, r3
	lis r4, lbl_1_bss_14E4@ha
	lha r3, lbl_1_bss_14E4@l(r4)
	cmpwi r3, 0x0
	beq .L_dist_ok
	cmpwi r3, 0x7
	beq .L_dist_ok
	cmpwi r3, 0x5
	beq .L_dist_ok
	cmpwi r3, 0x6
	bne .L_dist_exit
.L_dist_ok:
	lis r4, lbl_1_bss_1278@ha
	addi r4, r4, lbl_1_bss_1278@l
	lha r0, 0x6(r4)
	cmpwi r0, 0x0
	li r5, 0x4
	beq .L_dist_party
	li r5, 0x2
	cmpwi r12, 0x1
	bne .L_dist_exit
	b .L_dist_max_init
.L_dist_party:
	addi r0, r12, -0x1
	cmplwi r0, 0x2
	bgt .L_dist_exit
.L_dist_max_init:
	cmpwi r3, 0x7
	beq .L_unl_init
	cmpwi r3, 0x5
	bne .L_mag_init
	lis r6, lbl_1_bss_14EC@ha
	addi r6, r6, lbl_1_bss_14EC@l
	li r7, 0x0
	li r8, 0x7FFF
.L_dist_max:
	slwi r9, r7, 1
	lhax r10, r6, r9
	cmpw r10, r8
	bge .L_dist_skip
	mr r8, r10
.L_dist_skip:
	addi r7, r7, 0x1
	cmpw r7, r5
	blt .L_dist_max
	b .L_dist_digits
.L_unl_init:
	lis r6, lbl_1_bss_unl@ha
	addi r6, r6, lbl_1_bss_unl@l
	li r7, 0x0
	li r8, 0x0
.L_unl_max:
	slwi r9, r7, 1
	lhax r10, r6, r9
	cmpw r10, r8
	ble .L_unl_skip
	mr r8, r10
.L_unl_skip:
	addi r7, r7, 0x1
	cmpw r7, r5
	blt .L_unl_max
	b .L_dist_digits
.L_mag_init:
	lis r6, lbl_1_rodata_FF8@ha
	addi r6, r6, lbl_1_rodata_FF8@l
	lbzx r0, r6, r3
	lis r6, lbl_1_bss_10D4@ha
	addi r6, r6, lbl_1_bss_10D4@l
	add r6, r6, r0
	li r7, 0x0
	li r8, 0x0
.L_mag_max:
	mulli r9, r7, 0x2a
	lhax r10, r6, r9
	cmpw r10, r8
	ble .L_mag_skip
	mr r8, r10
.L_mag_skip:
	addi r7, r7, 0x1
	cmpw r7, r5
	blt .L_mag_max
.L_dist_digits:
	lis r6, lbl_1_bss_14F4@ha
	addi r6, r6, lbl_1_bss_14F4@l
	li r0, 0x0
	stb r0, 0xc(r6)
	li r7, 0xb
	li r9, 0xa
.L_dist_digit:
	divwu r10, r8, r9
	mullw r11, r10, r9
	subf r11, r11, r8
	addi r11, r11, 0x30
	stbx r11, r6, r7
	subi r7, r7, 0x1
	mr r8, r10
	cmpwi r8, 0x0
	bne .L_dist_digit
	add r4, r6, r7
	addi r4, r4, 0x1
	li r3, 0x4
	li r5, 0x4
	bl fn_1_2944
.L_dist_exit:
	lwz r0, 0x14(r1)
	mtlr r0
	addi r1, r1, 0x10
	blr
.endfn fn_1_dist_ins

.fn fn_1_bonus_hooks, global
.L_bonus_hook1:
	lis r7, lbl_1_bss_14E4@ha
	addi r7, r7, lbl_1_bss_14E4@l
	sth r28, 0x0(r7)
	lha r8, 0x2(r7)
	cmpwi r28, 0x3
	blt .L_bonus_main
	subi r9, r28, 0x2
	li r28, 0x0
	b .L_bonus_pick
.L_bonus_main:
	li r9, 0x0
.L_bonus_pick:
	slwi r9, r9, 1
	add r9, r9, r8
	mulli r9, r9, 0xc0
	lis r5, lbl_1_rodata_1008@ha
	addi r5, r5, lbl_1_rodata_1008@l
	add r5, r5, r9
	b .L_bonus_back1
.L_bonus_hook2:
	lis r3, lbl_1_bss_14E4@ha
	lha r3, lbl_1_bss_14E4@l(r3)
	b .L_bonus_back2
.endfn fn_1_bonus_hooks
"""

# Inline code run after the last stat of an entry is stored in fn_1_56C. It copies
# the player's step counter into lbl_1_bss_14EC[entry]. r31 = entry index and
# 0x8(r1) = halfword player order. All scratch registers are dead at these points.
DIST_PARTY = """\
	extsh r3, r31
	slwi r4, r3, 1
	addi r5, r1, 0x8
	lhax r6, r5, r4
	mulli r6, r6, 0x108
	lis r7, lbl_80282E70@ha
	addi r7, r7, lbl_80282E70@l
	add r7, r7, r6
	lha r8, 0x106(r7)
	lis r3, lbl_1_bss_14EC@ha
	addi r3, r3, lbl_1_bss_14EC@l
	sthx r8, r3, r4
	lha r8, 0x104(r7)
	lis r3, lbl_1_bss_unl@ha
	addi r3, r3, lbl_1_bss_unl@l
	sthx r8, r3, r4
"""
DIST_TAG = """\
	extsh r3, r31
	slwi r4, r3, 2
	addi r5, r1, 0x8
	lhax r6, r5, r4
	addi r4, r4, 0x2
	lhax r0, r5, r4
	mulli r6, r6, 0x108
	mulli r0, r0, 0x108
	lis r7, lbl_80282E70@ha
	addi r7, r7, lbl_80282E70@l
	add r6, r7, r6
	add r0, r7, r0
	lha r6, 0x106(r6)
	lha r0, 0x106(r0)
	add r8, r6, r0
	slwi r4, r3, 1
	lis r3, lbl_1_bss_14EC@ha
	addi r3, r3, lbl_1_bss_14EC@l
	sthx r8, r3, r4
	extsh r3, r31
	slwi r4, r3, 2
	addi r5, r1, 0x8
	lhax r6, r5, r4
	addi r4, r4, 0x2
	lhax r0, r5, r4
	mulli r6, r6, 0x108
	mulli r0, r0, 0x108
	add r6, r7, r6
	add r0, r7, r0
	lha r6, 0x104(r6)
	lha r0, 0x104(r0)
	add r8, r6, r0
	slwi r4, r3, 1
	lis r3, lbl_1_bss_unl@ha
	addi r3, r3, lbl_1_bss_unl@l
	sthx r8, r3, r4
"""

STAT_NEW = """\
	lis r7, lbl_1_rodata_FF8@ha
	addi r7, r7, lbl_1_rodata_FF8@l
	lbzx r0, r7, r3
	cmplwi r0, 0xFE
	beq .L_bonus_stat_unl
	cmplwi r0, 0xFF
	bne .L_bonus_stat_norm
	extsh r8, r31
	slwi r8, r8, 1
	lis r6, lbl_1_bss_14EC@ha
	addi r6, r6, lbl_1_bss_14EC@l
	lhax r6, r6, r8
	subfic r6, r6, 0x7FFF
	b .L_bonus_stat_done
.L_bonus_stat_unl:
	extsh r8, r31
	slwi r8, r8, 1
	lis r6, lbl_1_bss_unl@ha
	addi r6, r6, lbl_1_bss_unl@l
	lhax r6, r6, r8
	b .L_bonus_stat_done
.L_bonus_stat_norm:
	lhax r6, r5, r0
	lis r7, lbl_1_rodata_stat_extra@ha
	addi r7, r7, lbl_1_rodata_stat_extra@l
	slwi r8, r3, 2
	add r7, r7, r8
	li r9, 0x4
	mtctr r9
.L_bonus_stat_extra:
	lbz r0, 0x0(r7)
	cmpwi r0, 0x0
	beq .L_bonus_stat_done
	lhax r0, r5, r0
	add r6, r6, r0
	addi r7, r7, 0x1
	bdnz .L_bonus_stat_extra
.L_bonus_stat_done:
"""


def replace_once(text, old, new, what):
    if text.count(old) != 1:
        raise RuntimeError(f"{what}: expected exactly one match, found {text.count(old)}")
    return text.replace(old, new, 1)


def patch_asm():
    if not ASM_PRE.exists():  # first run on a fresh build: asm/ is still the pristine dtk split
        shutil.copytree(ASM, ASM_PRE)
    for path in (TEXT, RODATA, BSS):
        shutil.copyfile(ASM_PRE / path.name, path)
    text = TEXT.read_text()

    # fn_1_17BF8: three fixed calls -> driver.
    old = (
        "/* 00017EF4 00017FD0  38 60 00 00 */\tli r3, 0x0\n"
        "/* 00017EF8 00017FD4  4B FF A5 65 */\tbl fn_1_1245C\n"
        "/* 00017EFC 00017FD8  38 60 00 01 */\tli r3, 0x1\n"
        "/* 00017F00 00017FDC  4B FF A5 5D */\tbl fn_1_1245C\n"
        "/* 00017F04 00017FE0  38 60 00 02 */\tli r3, 0x2\n"
        "/* 00017F08 00017FE4  4B FF A5 55 */\tbl fn_1_1245C\n"
    )
    text = replace_once(text, old, "\tbl fn_1_bonus_run\n" + "\tnop\n" * 5, "driver call")

    # fn_1_1245C hook 1: table select.
    old = (
        "/* 00012478 00012554  3C 60 00 00 */\tlis r3, lbl_1_rodata_4A8@ha\n"
        "/* 0001247C 00012558  38 A3 00 00 */\taddi r5, r3, lbl_1_rodata_4A8@l\n"
    )
    text = replace_once(text, old, "\tb .L_bonus_hook1\n\tnop\n.L_bonus_back1:\n", "table select")

    # fn_1_1245C hook 2: real id for the stat lookup.
    old = (
        ".L_000125D8:\n"
        "/* 000125D8 000126B4  7F 83 E3 78 */\tmr r3, r28\n"
        "/* 000125DC 000126B8  38 81 00 0A */\taddi r4, r1, 0xa\n"
    )
    text = replace_once(text, old, ".L_000125D8:\n\tb .L_bonus_hook2\n.L_bonus_back2:\n\taddi r4, r1, 0xa\n", "stat id")

    # fn_1_122F0: per-award stat offset.
    old = (
        "/* 00012348 00012424  7C 60 07 34 */\textsh r0, r3\n"
        "/* 0001234C 00012428  54 00 08 3C */\tslwi r0, r0, 1\n"
        "/* 00012350 0001242C  7C A5 02 14 */\tadd r5, r5, r0\n"
        "/* 00012354 00012430  A8 C5 00 0A */\tlha r6, 0xa(r5)\n"
    )
    text = replace_once(text, old, STAT_NEW, "stat offset")

    # fn_1_56C: copy the step counter into the per-entry array.
    old = "/* 00000EF8 00000FD4  B1 05 00 26 */\tsth r8, 0x26(r5)\n"
    text = replace_once(text, old, old + DIST_PARTY, "party distance")
    old = "/* 00001838 00001914  B0 A3 00 26 */\tsth r5, 0x26(r3)\n"
    text = replace_once(text, old, old + DIST_TAG, "tag distance")

    # fn_1_56C: the Mini-game Star stat (entry +0x0A) is minigames won (GwPlayer+0x2A,
    # counted by apply_minigame_wins_patch.py) instead of minigame coins (+0x1E).
    # The +0x14 stat-page copy stays coins. Tag mode takes the higher of the two
    # teammates (they win together) instead of the sum.
    old = "/* 00000B74 00000C50  A8 83 00 1E */\tlha r4, 0x1e(r3)\n"
    text = replace_once(text, old, "\tlha r4, 0x2a(r3)\n", "party mg wins")
    old = "/* 0000114C 00001228  A8 03 00 1E */\tlha r0, 0x1e(r3)\n"
    text = replace_once(text, old, "\tlha r0, 0x2a(r3)\n", "tag mg wins 1")
    old = (
        "/* 00001178 00001254  A8 A3 00 1E */\tlha r5, 0x1e(r3)\n"
        "/* 0000117C 00001258  7C 80 2A 14 */\tadd r4, r0, r5\n"
    )
    text = replace_once(text, old, (
        "\tlha r5, 0x2a(r3)\n"
        "\tmr r4, r0\n"
        "\tcmpw r5, r0\n"
        "\tble .L_bonus_tag_mgmax\n"
        "\tmr r4, r5\n"
        ".L_bonus_tag_mgmax:\n"), "tag mg wins 2")

    old = "/* 00012AD0 00012BAC  41 80 FF 50 */\tblt .L_00012A20\n"
    text = replace_once(text, old, old + "\tclrlwi r3, r29, 24\n\tbl fn_1_dist_ins\n", "party distance insert")
    old = ".L_0001350C:\n"
    text = replace_once(text, old, old + "\tclrlwi r3, r29, 24\n\tbl fn_1_dist_ins\n", "tag distance insert")

    TEXT.write_text(text.rstrip("\n") + "\n" + NEW_TEXT)
    RODATA.write_text(RODATA.read_text().rstrip("\n") + "\n" + rodata_block())
    BSS.write_text(BSS.read_text().rstrip("\n") + "\n" + BSS_BLOCK)


# ---- DOL ------------------------------------------------------------------

CAVE = 0x80003F18   # zero-filled, up to 0x800041E4

STB_MOVENUM = 0x9804000A   # stb r0, 0xa(r4)
STH_CAPSULE = 0xB0A30034   # sth r5, 0x34(r3)
WINS_RESET = 0x8014C00C
STH_MGBONUS = 0xB0A30028   # sth r5, 0x28(r3)
STW_MGBONUS = 0x90A30028   # stw r5, 0x28(r3): also zeroes +0x2A


def dol_cave_a(back):
    # stb r0,0xa(r4); lhz r5,0x106(r4); addi r5,r5,1; sth r5,0x106(r4); b back
    return [STB_MOVENUM, 0xA0A40106, 0x38A50001, 0xB0A40106], back


STH_STEPS = 0xB0A30106   # sth r5, 0x106(r3): earlier version of the cave
STW_STEPS = 0x90A30104   # stw r5, 0x104(r3): steps (+0x106) and Unlucky (+0x104)


def dol_cave_c(back):
    # sth r5,0x34(r3); stw r5,0x104(r3) (r5 is 0 here; zeroes +0x104 Unlucky, apply_unlucky_patch.py,
    # and +0x106 steps); b back
    return [STH_CAPSULE, STW_STEPS], back


CMPWI_R28_0 = 0x2C1C0000   # cmpwi r28, 0
BNE_SKIP_COUNT = 0x40820068  # bne .L_801D47D0
NOP = 0x60000000
TRAP_CAVE = 0x80004018  # zero-filled, after the step-counter caves


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    # fn_801D44B8 bumps GwPlayer+0x16 (orbs landed on) only on the landing path
    # (r28 == 0). Orbs that trigger when passed (orb type 2) never reach that code:
    # the pass-over path (r28 != 0) goes straight to the trigger check at 0x801D4668.
    # Count there instead (r30 = player), capped at 99 like the landing count.
    #
    # An earlier version hooked 0x801D4764/68 (the landing counter) with a cave that also
    # tried to count trap orbs when r28 != 0; that code was unreachable, so restore it.
    for address, vanilla in ((0x801D4764, CMPWI_R28_0), (0x801D4768, BNE_SKIP_COUNT)):
        struct.pack_into(">I", dol, dol_offset(dol, address), vanilla)

    hook, back = 0x801D4668, 0x801D466C
    cave = TRAP_CAVE
    # 10 words: 0x80004018-0x80004040 is all that is free here (star_shuffle_bet owns
    # 0x80004040 onwards, whomp_rich ends at 0x80004018).
    words = [
        0x1C9E0108,                        # mulli r4, r30, 0x108
        0x3C608028,                        # lis r3, 0x8028
        0x7C841A14,                        # add r4, r4, r3
        0x88642E86,                        # lbz r3, 0x2E86(r4)  (player table 0x80282E70 + 0x16)
        0x38630001,                        # addi r3, r3, 1
        0x28030063,                        # cmplwi r3, 99
        0x41810008,                        # bgt +8 (already capped: skip the store)
        0x98642E86,                        # stb r3, 0x2E86(r4)
        0x7F63DB78,                        # mr r3, r27 (displaced instruction)
        encode_branch(cave + 36, back),
    ]
    cave_off = dol_offset(dol, cave)
    old = bytes(dol[cave_off:cave_off + 4 * len(words)])
    new = struct.pack(f">{len(words)}I", *words)
    old_head = struct.unpack_from(">I", old)[0]
    if old != new and any(old) and old_head not in (CMPWI_R28_0, 0x1C9E0108):  # earlier versions
        raise RuntimeError(f"Cave at {cave:#x} is not empty")
    dol[cave_off:cave_off + len(new)] = new
    off = dol_offset(dol, hook)
    current = struct.unpack_from(">I", dol, off)[0]
    want = encode_branch(hook, cave)
    if current not in (0x7F63DB78, want):
        raise RuntimeError(f"Unexpected word at {hook:#x}: {current:#010x}")
    struct.pack_into(">I", dol, off, want)
    # Board init zeroes mgCoinBonus with sth r5,0x28(r3) (r5 = 0). Widen it to stw so it
    # also zeroes +0x2A, the minigames-won counter (apply_minigame_wins_patch.py). No cave:
    # the caves after 0x80003F4C belong to apply_whomp_rich_patch.py.
    off = dol_offset(dol, WINS_RESET)
    current = struct.unpack_from(">I", dol, off)[0]
    if current not in (STH_MGBONUS, STW_MGBONUS):
        raise RuntimeError(f"Unexpected word at {WINS_RESET:#x}: {current:#010x}")
    struct.pack_into(">I", dol, off, STW_MGBONUS)
    cursor = CAVE
    plan = [
        (0x80154BE8, STB_MOVENUM, dol_cave_a(0x80154BEC)),
        (0x801A0808, STB_MOVENUM, dol_cave_a(0x801A080C)),
        (0x8014C024, STH_CAPSULE, dol_cave_c(0x8014C028)),
    ]
    for hook, vanilla, (words, back) in plan:
        words = words + [encode_branch(cursor + 4 * len(words), back)]
        hook_off = dol_offset(dol, hook)
        current = struct.unpack_from(">I", dol, hook_off)[0]
        want = encode_branch(hook, cursor)
        if current not in (vanilla, want):
            raise RuntimeError(f"Unexpected word at {hook:#x}: {current:#010x}")
        struct.pack_into(">I", dol, hook_off, want)
        cave_off = dol_offset(dol, cursor)
        old = bytes(dol[cave_off:cave_off + 4 * len(words)])
        new = struct.pack(f">{len(words)}I", *words)
        older = new.replace(struct.pack(">I", STW_STEPS), struct.pack(">I", STH_STEPS))
        if old != new and any(old) and old != older:
            raise RuntimeError(f"Cave at {cursor:#x} is not empty")
        dol[cave_off:cave_off + len(new)] = new
        cursor += 4 * len(words)
    DOL.write_bytes(dol)


# ---- messages -------------------------------------------------------------

HEADER = b"\x00\x15\x00\x02"
FF = b"\xff"


def enc(text):
    """Encode text. {cN} -> start colour N (1E 0N), {e} -> end colour (1E 08)."""
    out = b""
    i = 0
    while i < len(text):
        if text[i] == "{":
            j = text.index("}", i)
            tag = text[i + 1:j]
            if tag == "e":
                out += b"\x1e\x08"
            elif tag[0] == "#":
                out += bytes([0x1F, int(tag[1:])])
            else:
                out += bytes([0x1E, int(tag[1:])])
            i = j + 1
            continue
        if text.startswith("...", i) and not text.startswith("....", i):
            out += b"\x85"
            i += 3
            continue
        c = text[i]
        out += {" ": b"\x10", "!": b"\xc2", "?": b"\xc3", "'": b"\x5c", "-": b"=",
                "\n": b"\x0a", ",": b"\x82"}.get(c, c.encode("ascii"))
        i += 1
    return out


def pages(record):
    """Split a record (after its 4-byte header) into pages; FF ends a page."""
    body = record[4:].rstrip(b"\0")
    assert body.endswith(FF), "record does not end with a page break"
    return body[:-1].split(FF)


def join(*page_list):
    return HEADER + FF.join(page_list) + FF + b"\0\0"


def star_records(open_p, open_t, color, name, plural, party_intro, two, three, none,
                 tag_intro, tag_none, names=()):
    """Eight records (plus optional winner-name records) for a new award.
    Texts use {c} for the award colour."""
    def e(text):
        return enc(text.replace("{c}", "{c%d}" % color))
    p_intro = [e(t) for t in party_intro]
    t_intro = [e(t) for t in tag_intro]
    return [
        join(*p_intro),
        join(*open_p, *p_intro),
        join(e(two)),
        join(e(three)),
        join(e(none)),
        join(*t_intro),
        join(*open_t, *t_intro),
        join(e(tag_none)),
    ] + [join(*(e(t) for t in page_list)) for page_list in names]


def build_records(records):
    open_p = pages(records[0x05])[:2]
    open_t = pages(records[0x1D])[:2]
    mg_p = pages(records[0x05])
    mg_t = pages(records[0x1D])
    act_t = pages(records[0x25])
    # Tag intro page 3 said "won the most coins in mini-games"; the star now counts wins.
    mg_t[3] = enc("This award goes to the team that won\nthe most mini-games...")
    new = [
        # party
        join(enc("Next, we will award the {c3}Mini-game Star{e}..."), *mg_p[3:]),
        join(*open_p, *pages(records[0x37])),
        join(*open_p, *pages(records[0x13])),
        join(*open_p, *pages(records[0x0F])),
        # tag
        join(enc("Next, we'll award the {c3}Mini-game Star{e}..."), *mg_t[3:]),
        join(*open_t, *pages(records[0x3B])),
        join(enc("Next up is the {c5}Action Star{e}..."), *act_t[1:]),
        join(*open_t, enc("Next up is the {c5}Action Star{e}..."), *act_t[1:]),
        join(*open_t, *pages(records[0x23])),
    ]
    heart_list = "That's {c}?{e}, {c}Duel{e}, {c}Miracle{e}, {c}DK{e} and\n{c}Bowser Spaces{e}, all added up!"
    new += star_records(
        open_p, open_t, HEART_COLOR, "Heart", "Hearts",
        ["Next up is the {c}Heart Star{e}!",
         "This Star goes to whoever landed on\nthe most special spaces...",
         heart_list,
         "The {c}Heart Star{e} goes to........."],
        "How sweet! There are two\n{c}Heart Star{e} winners!",
        "Whoa! There are three {c}Heart Star{e}\nwinners!",
        "Nobody landed on a single special\nspace? How peaceful!",
        ["Next up is the {c}Heart Star{e}...",
         "The team that landed on the most\nspecial spaces receives this Star...",
         heart_list,
         "The {c}Heart Star{e} winner is........."],
        "Wow! Nobody landed on a special space?!")
    new += star_records(
        open_p, open_t, DIST_COLOR, "Distance", "Distances",
        ["Now for the {c}Distance Star{e}!",
         "This Star goes to whoever traveled\nthe LEAST around the board...",
         "The {c}Distance Star{e} goes to........."],
        "Impressive! There are two\n{c}Distance Star{e} winners!",
        "Remarkable! There are three\n{c}Distance Star{e} winners!",
        "Everybody moved the same amount?!\nHow boring!",
        ["Now for the {c}Distance Star{e}...",
         "The team that traveled the least\naround the board receives this Star...",
         "The {c}Distance Star{e} winner is........."],
        "What?! Both teams moved the same amount?!",
        names=[
            ["{c7}{#1}{e}!", "This good lad barely moved...\nHe only traveled {#5} spaces! HAHAHAHA!"],
            ["{c7}{#1}{e} and {c7}{#2}{e}!", "These good lads barely moved...\nThey only traveled {#5} spaces! HAHAHAHA!"],
            ["{c7}{#1}{e}, {c7}{#2}{e}, and {c7}{#3}{e}!", "These good lads barely moved...\nThey only traveled {#5} spaces! HAHAHAHA!"],
            ["{c7}{#1}{e} and {c7}{#2}{e} of team\n{c5}{#3}{e}!", "These good lads barely moved...\nThey only traveled {#5} spaces! HAHAHAHA!"],
        ])
    new += star_records(
        open_p, open_t, MAGNET_COLOR, "Trap Merchant", "Trap Merchants",
        ["Now for the {c}Trap Merchant Star{e}!",
         "This Star goes to whoever landed on or\nset off the most {c}Orbs{e}...",
         "The {c}Trap Merchant Star{e} goes to........."],
        "Unlucky! There are two\n{c}Trap Merchant Star{e} winners!",
        "Oh dear! There are three\n{c}Trap Merchant Star{e} winners!",
        "Nobody set off a single Orb?!\nThe board must have been spotless!",
        ["Now for the {c}Trap Merchant Star{e}...",
         "The team that set off the most\n{c}Orbs{e} receives this Star...",
         "The {c}Trap Merchant Star{e} winner is........."],
        "What?! Nobody set off an Orb?!",
        names=[
            ["{c7}{#1}{e}!", "This good lad sure loved traps...\nHe set off {#5} of them!"],
            ["{c7}{#1}{e} and {c7}{#2}{e}!", "These good lads sure loved traps...\nThey each set off {#5} of them!"],
            ["{c7}{#1}{e}, {c7}{#2}{e}, and {c7}{#3}{e}!", "These good lads sure loved traps...\nThey each set off {#5} of them!"],
            ["{c7}{#1}{e} and {c7}{#2}{e} of team\n{c5}{#3}{e}!", "These good lads sure loved traps...\nThey set off {#5} of them!"],
        ])
    wins = "What a champ! Total {c3}Mini-game{e}\nwins: {#5}!"
    wins_n = "What champs! Each one won\n{#5} {c3}Mini-games{e}!"
    new += [
        join(*open_t, *mg_t[2:]),
        join(enc("{c7}{#1}{e}!"), enc(wins)),
        join(enc("{c7}{#1}{e} and {c7}{#2}{e}!"), enc(wins_n)),
        join(enc("{c7}{#1}{e}, {c7}{#2}{e}, and {c7}{#3}{e}!"), enc(wins_n)),
        join(enc("{c7}{#1}{e} and {c7}{#2}{e} of team\n{c5}{#3}{e}!"),
             enc("What a team! Total {c3}Mini-game{e}\nwins: {#5}!")),
    ]
    # Unlucky Star (UNLUCKY_BASE): after the Mini-game records.
    new += star_records(
        open_p, open_t, UNLUCKY_COLOR, "Unlucky", "Unluckies",
        ["Now for the {c}Unlucky Star{e}!",
         "This Star goes to whoever lost the\nmost coins and Stars to bad luck...",
         "Every Star lost counts as 30 coins!",
         "The {c}Unlucky Star{e} goes to........."],
        "Ouch! There are two\n{c}Unlucky Star{e} winners!",
        "Yikes! There are three\n{c}Unlucky Star{e} winners!",
        "Nobody lost a thing?!\nWhat a lucky bunch!",
        ["Now for the {c}Unlucky Star{e}...",
         "The team that lost the most coins and\nStars to bad luck receives this Star...",
         "Every Star lost counts as 30 coins!",
         "The {c}Unlucky Star{e} winner is........."],
        "What?! Neither team lost a thing?!",
        names=[
            ["{c7}{#1}{e}!", "What rotten luck! That's {#5}\ncoins' worth of losses!"],
            ["{c7}{#1}{e} and {c7}{#2}{e}!", "What rotten luck! That's {#5}\ncoins' worth of losses each!"],
            ["{c7}{#1}{e}, {c7}{#2}{e}, and {c7}{#3}{e}!", "What rotten luck! That's {#5}\ncoins' worth of losses each!"],
            ["{c7}{#1}{e} and {c7}{#2}{e} of team\n{c5}{#3}{e}!", "What rotten luck! That's {#5}\ncoins' worth of losses!"],
        ])
    return [r + b"\0" * (-len(r) % 4) for r in new]


def patch_messages():
    data = bytearray(MESS_SOURCE.read_bytes())
    section_count = struct.unpack_from(">I", data, 0)[0]

    def start(index):
        return 4 + struct.unpack_from(">I", data, 4 + 4 * index)[0]

    base, end = start(BANK), start(BANK + 1)
    count = struct.unpack_from(">I", data, base)[0]
    if count != ORIGINAL_COUNT:
        raise RuntimeError(f"Unexpected bank 0x0E record count: {count}")

    offsets = [struct.unpack_from(">I", data, base + 4 + 4 * i)[0] for i in range(count)]
    bounds = [base + 4 + o for o in offsets] + [end]
    records = [bytes(data[bounds[i]:bounds[i + 1]]) for i in range(count)]
    # Coin Star gets its own colour (vanilla shares the Orb Star's colour 6).
    for i in (0x0F, 0x10, 0x11, 0x23):
        records[i] = records[i].replace(b"\x1e\x06", bytes([0x1E, COIN_COLOR]))
    records += build_records(records)
    assert len(records) == ORIGINAL_COUNT + NEW_COUNT

    position = 4 + 4 * len(records)
    new_offsets = []
    for record in records:
        new_offsets.append(position - 4)
        position += len(record)
    block = struct.pack(">I", len(records)) + struct.pack(f">{len(records)}I", *new_offsets)
    block += b"".join(records)
    delta = len(block) - (end - base)
    data[base:end] = block
    for index in range(BANK + 1, section_count):
        pos = 4 + 4 * index
        struct.pack_into(">I", data, pos, struct.unpack_from(">I", data, pos)[0] + delta)
    write_bank(MESS_OUTPUT, MESS_SOURCE, data, BANK)


def deploy():
    """Copy the rebuilt REL, English messages and DOL into the extracted game root."""
    shutil.copyfile(DLL / "mdpresultdll.rel", GAME_ROOT / "dll/mdpresultdll.rel")
    shutil.copyfile(MESS_OUTPUT, GAME_ROOT / "mess/messdata_eng.bin")
    shutil.copyfile(DOL, GAME_ROOT / "&&systemdata/Start.dol")
    print(f"deployed to {GAME_ROOT}")


def main():
    patch_asm()
    patch_messages()
    patch_dol()
    from tools.lib import rebuild_mdpresult
    rebuild_mdpresult.main()
    deploy()


if __name__ == "__main__":
    sys.exit(main())
