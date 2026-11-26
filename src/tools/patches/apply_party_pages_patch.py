"""Pages on the party board select: boards beyond MP6's six sit on further pages of six icons.

The board select (mdpartydll; map in docs/board-tables.md, "Party menu and results") has exactly six of
everything per board: icon model copies 11-16, texture animations 12-17 (`lbl_1_bss_800`), half-disc
sprite animations 3-14 (`lbl_1_bss_93C`), name banner sprites (group 1), unlock flags (`lbl_1_data_C66`)
and the board DLL table (`lbl_1_rodata_7C`). Instead of growing those full tables, the cursor stays a slot
(0-5) and a page number picks what the six slots show: page 0 is MP6's boards, page p >= 1 holds
EXTRA_BOARDS[(p - 1) * 6 + slot]. Turning the page rewrites the six slots' entries in those tables
(fn_1_pg_apply), so all of the menu's own code shows and launches the page's boards unchanged:
  * icon picture: texture animation 12 + slot = the board's ICON file (or EMPTY_ICON on a slot with no
    board), re-applied to the six icon models as fn_1_19510 does;
  * half-disc: sprite animations 3 + 2 slot / 4 + 2 slot = the board's day / night pictures;
  * name banner: HuSprBankSet(group 1, slot, p) (group 1's id is `lbl_1_bss_918`+2; the banner files of that
    slot get one bank per page; apply_pagoda_board_patch.py adds Pagoda Peak's as bank 1 of slot 0's files).
    The first build passed a sprite id instead of the group and member: a stray bank on another sprite gave
    invalid reads in HuSprCall (0x8000EBF4) and the banner never changed;
  * unlock flag 1 for a board, 0 (the locked look) for an empty slot; DLL table = the board's overlay.
Page 0's entries are saved when the menu first leaves page 0 and put back on returning to it.

The cursor moves over the boards that exist (pages fill from slot 0): left of slot 0 is the previous page's
last board, right of a page's last board is the next page's slot 0, wrapping over all pages. Empty slots
show the locked icon and are never selected, so the vanilla "buy it at the Star Bank" text never appears.

Hooks (word for word, so no .text offset moves and clone_board's offset-based hooks still match):
  * fn_1_188BC .text 0x18958-0x18990 / 0x18AC4-0x18AFC (cursor left / right with the wrap at 6):
    `bl fn_1_pg_left` / `bl fn_1_pg_right`, then nops;
  * fn_1_19510 0x1954C `sth r0,0x4(r3)` (cursor = 0 when the screen opens): `bl fn_1_pg_home`, which also
    goes back to page 0;
  * fn_1_918 0xA10 `lha r0,0x4(r3)` (the cursor written as the board number before launch):
    `bl fn_1_pg_board_no` (page p > 0: the board's own number, e.g. 11);
  * fn_1_305E0 0x30658 `sth r3,0x4(r31)` (the cursor restored from the board number after a game, for
    "play again"): `bl fn_1_pg_return` (an extra board's number gives its page and slot);
  * the launch (fn_1_129C, fn_1_2DF8C) indexes the DLL table by the board number, which clone_board's stub
    turns from 11 into its alias 3 (clone.ALIAS), not by the cursor. So fn_1_pg_board_no (launch) and
    fn_1_pg_return ("play again") also write the extra board's overlay into entry ALIAS; turning back to page 0
    restores it. (First Dolphin test, 2026-11-26: without this, Pagoda Peak's icon started Snowflake Lake.)
  * fn_1_39E00 0x3A16C, 0x3A5D0 `addis r3,r3,0x2` (description message 0x20009 + cursor):
    `bl fn_1_pg_desc` (page p > 0: + 6 + (p - 1) * 6, so extra board e uses bank 2 record 15 + e);
  * fn_1_2E380 0x2F0B0 `bl HuPrcChildCreate` (end of the loader): `bl fn_1_pg_init_child`, which loads
    the extra boards' animations (HuDataSelHeapReadNum + HuSprAnimRead, as the loader does) first.

Rebuilds mdpartydll from a pristine asm snapshot (asm_pre_pages/) with tools.lib.rebuild_mdpresult, so it is
safe to re-run; the REL is build/GP6P01/mdpartydll/mdpartydll.rel, which apply_clone_board_patch.py hooks
and installs as files/dll/mdpartydll.rel. Runs ninja (the REL target only), so it goes before mgtable_move.
The files it names (ICON, day and night pictures, EMPTY_ICON, the banner banks, the description) are written
by apply_pagoda_board_patch.py; without them the board select would fail to load its pictures.

Status: built 2026-11-25. Dolphin tests on 2026-11-26 found three bugs, all fixed the same day: the menu ran
out of memory (select_art.py), the banner bank call took a sprite id, and Pagoda Peak launched Snowflake Lake
(the DLL table entry ALIAS). The fixed build was retested and confirmed by the user in Dolphin (2026-11-26).
"""
import shutil
import sys
from dataclasses import dataclass

from tools.lib import rebuild_mdpresult
from tools.patches.apply_clone_board_patch import ALIAS
from tools.lib.paths import ROOT

DLL = ROOT / "build/GP6P01/mdpartydll"
ASM = DLL / "asm"
ASM_PRE = DLL / "asm_pre_pages"
TEXT = ASM / "auto_00_00000000_text.s"
DATA = ASM / "auto_04_00000000_data.s"
BSS = ASM / "auto_05_00000000_bss.s"
REL_BUILT = DLL / "mdpartydll.rel"

SLOTS = 6
MDPARTY_DIR = 0x9F0000          # data numbers of data/mdparty.bin
MDPARTY_FILES = 254             # files in the vanilla mdparty.bin; new ones are appended from here


@dataclass(frozen=True)
class ExtraBoard:
    board_no: int               # GwSystem board number the board REL sets (and fn_1_918 writes)
    overlay: int                # its DLL (the board select's DLL table entry)
    icon: int                   # mdparty.bin file: 512x256 octagon picture, 2 banks (day, night)
    disc_day: int               # mdparty.bin file: 256x256 half-disc picture by day
    disc_night: int             # ... by night


EMPTY_ICON = MDPARTY_FILES      # the icon of a page slot with no board
EXTRA_BOARDS = (
    ExtraBoard(board_no=11, overlay=0x70, icon=MDPARTY_FILES + 1, disc_day=MDPARTY_FILES + 2,
               disc_night=MDPARTY_FILES + 3),    # Pagoda Peak (apply_pagoda_board_patch.py)
)
NEW_FILES = MDPARTY_FILES + 1 + 3 * len(EXTRA_BOARDS)
DESC_FIRST = 15                 # bank 2 record of extra board 0's description (0x20009 + 6)

HuSprBankSet = "fn_8000FF94"           # (group, member, bank)
HuDataSelHeapReadNum = "fn_80008DD4"
HuSprAnimRead = "fn_8000F07C"
Hu3DAnimAnimSet = "fn_80030D54"
Hu3DAnimBankSet = "fn_80031438"
HuPrcChildCreate = "fn_8000DA98"
GwSystem = "lbl_80283290"

# (text offset, the vanilla instruction, its replacement); a block is its first word's bl then nops
LEFT = [(0x18958 + 4 * i, None, "nop") for i in range(15)]
RIGHT = [(0x18AC4 + 4 * i, None, "nop") for i in range(15)]
LEFT[0] = (0x18958, "lis r3, lbl_1_bss_9F4@ha", "bl fn_1_pg_left")
LEFT[14] = (0x18990, "sth r0, 0x4(r4)", "nop")
RIGHT[0] = (0x18AC4, "lis r3, lbl_1_bss_9F4@ha", "bl fn_1_pg_right")
RIGHT[14] = (0x18AFC, "sth r0, 0x4(r4)", "nop")
BLOCK_INNER = {offset for offset, _, _ in LEFT[:-1] + RIGHT[:-1]}
HOOKS = LEFT + RIGHT + [
    (0x1954C, "sth r0, 0x4(r3)", "bl fn_1_pg_home"),
    (0x00A10, "lha r0, 0x4(r3)", "bl fn_1_pg_board_no"),
    (0x30658, "sth r3, 0x4(r31)", "bl fn_1_pg_return"),
    (0x3A16C, "addis r3, r3, 0x2", "bl fn_1_pg_desc"),
    (0x3A5D0, "addis r3, r3, 0x2", "bl fn_1_pg_desc"),
    (0x2F0B0, f"bl {HuPrcChildCreate}", "bl fn_1_pg_init_child"),
]

BOARD_ROW = 0x14                # lbl_1_data_pg_boards: board_no, overlay, icon, disc day, disc night
ANIM_ROW = 0xC                  # lbl_1_bss_pg_anim: icon, day, night (ANIMDATA *)
# lbl_1_bss_pg_orig: page 0's icon[6] +0x00, disc[12] +0x18, dll[6] +0x48, unlock[6] (s16) +0x60
ORIG_DISC, ORIG_DLL, ORIG_C66, ORIG_SIZE = 0x18, 0x48, 0x60, 0x70


def la(reg, sym):
    return f"\tlis {reg}, {sym}@ha\n\taddi {reg}, {reg}, {sym}@l\n"


def data_text():
    rows = "".join(f"\t.4byte 0x{b.board_no:X}, 0x{b.overlay:X}, 0x{MDPARTY_DIR | b.icon:08X}, "
                   f"0x{MDPARTY_DIR | b.disc_day:08X}, 0x{MDPARTY_DIR | b.disc_night:08X}\n" for b in EXTRA_BOARDS)
    return (f"\n# Board select pages (apply_party_pages_patch.py)\n.balign 4\n"
            f".obj lbl_1_data_pg_cfg, global\n\t.4byte {len(EXTRA_BOARDS)}\n"
            f"\t.4byte 0x{MDPARTY_DIR | EMPTY_ICON:08X}\n.endobj lbl_1_data_pg_cfg\n"
            f".obj lbl_1_data_pg_boards, global\n{rows}.endobj lbl_1_data_pg_boards\n")


def bss_text():
    return (f"\n# Board select pages (apply_party_pages_patch.py)\n.balign 4\n"
            f".obj lbl_1_bss_pg_page, global\n\t.skip 0x4\n.endobj lbl_1_bss_pg_page\n"
            f".obj lbl_1_bss_pg_empty, global\n\t.skip 0x4\n.endobj lbl_1_bss_pg_empty\n"
            f".obj lbl_1_bss_pg_anim, global\n\t.skip 0x{ANIM_ROW * len(EXTRA_BOARDS):X}\n.endobj lbl_1_bss_pg_anim\n"
            f".obj lbl_1_bss_pg_orig, global\n\t.skip 0x{ORIG_SIZE:X}\n.endobj lbl_1_bss_pg_orig\n")


# Register use: the leaf helpers (pg_desc, pg_board_no) replace a non-call instruction, so they keep every
# register but their result (r11, r12 and cr are saved). The others replace calls or whole blocks whose
# volatile registers are dead afterwards (checked in the vanilla listing), and save what they use.
TEXT_CODE = f"""
# Board select pages (apply_party_pages_patch.py): see its docstring.

# r3 = page -> r3 = boards on it (pages fill from slot 0)
.fn fn_1_pg_count, global
\tcmpwi r3, 0x0
\tbne .L_pg_count_extra
\tli r3, {SLOTS}
\tblr
.L_pg_count_extra:
{la("r12", "lbl_1_data_pg_cfg")}\tlwz r12, 0x0(r12)
\tsubi r3, r3, 0x1
\tmulli r3, r3, {SLOTS}
\tsubf r3, r3, r12
\tcmpwi r3, {SLOTS}
\tblelr
\tli r3, {SLOTS}
\tblr
.endfn fn_1_pg_count

# -> r3 = pages (1 + ceil(extra / 6))
.fn fn_1_pg_pages, global
{la("r3", "lbl_1_data_pg_cfg")}\tlwz r3, 0x0(r3)
\taddi r3, r3, {2 * SLOTS - 1}
\tli r12, {SLOTS}
\tdivwu r3, r3, r12
\tblr
.endfn fn_1_pg_pages

# r3 = page: the six slots show it (tables, banner banks, icon textures)
.fn fn_1_pg_apply, global
\tstwu r1, -0x50(r1)
\tmflr r0
\tstw r0, 0x54(r1)
\tstmw r27, 0x3c(r1)
\tmr r31, r3
{la("r3", "lbl_1_bss_pg_page")}\tstw r31, 0x0(r3)
\tli r30, 0x0
.L_pg_apply_slot:
{la("r29", "lbl_1_bss_pg_orig")}\tslwi r28, r30, 2
\tlwzx r0, r29, r28
\tstw r0, 0x8(r1)
\tslwi r27, r30, 3
\taddi r27, r27, 0x{ORIG_DISC:X}
\tadd r27, r29, r27
\tlwz r0, 0x0(r27)
\tstw r0, 0xc(r1)
\tlwz r0, 0x4(r27)
\tstw r0, 0x10(r1)
\taddi r27, r28, 0x{ORIG_DLL:X}
\tlwzx r0, r29, r27
\tstw r0, 0x18(r1)
\tslwi r27, r30, 1
\taddi r27, r27, 0x{ORIG_C66:X}
\tlhax r0, r29, r27
\tstw r0, 0x14(r1)
\tli r0, 0x0
\tstw r0, 0x1c(r1)
\tcmpwi r31, 0x0
\tbeq .L_pg_apply_write
\tsubi r3, r31, 0x1
\tmulli r3, r3, {SLOTS}
\tadd r3, r3, r30
{la("r4", "lbl_1_data_pg_cfg")}\tlwz r5, 0x0(r4)
\tcmpw r3, r5
\tblt .L_pg_apply_board
{la("r4", "lbl_1_bss_pg_empty")}\tlwz r0, 0x0(r4)
\tstw r0, 0x8(r1)
\tli r0, 0x0
\tstw r0, 0x14(r1)
\tb .L_pg_apply_write
.L_pg_apply_board:
\tmulli r5, r3, {ANIM_ROW}
{la("r4", "lbl_1_bss_pg_anim")}\tadd r4, r4, r5
\tlwz r0, 0x0(r4)
\tstw r0, 0x8(r1)
\tlwz r0, 0x4(r4)
\tstw r0, 0xc(r1)
\tlwz r0, 0x8(r4)
\tstw r0, 0x10(r1)
\tmulli r5, r3, {BOARD_ROW}
{la("r4", "lbl_1_data_pg_boards")}\tadd r4, r4, r5
\tlwz r0, 0x4(r4)
\tstw r0, 0x18(r1)
\tli r0, 0x1
\tstw r0, 0x14(r1)
\tstw r31, 0x1c(r1)
.L_pg_apply_write:
{la("r4", "lbl_1_bss_800")}\tadd r4, r4, r28
\tlwz r0, 0x8(r1)
\tstw r0, 0x30(r4)
{la("r4", "lbl_1_bss_93C")}\tslwi r5, r30, 3
\tadd r4, r4, r5
\tlwz r0, 0xc(r1)
\tstw r0, 0xc(r4)
\tlwz r0, 0x10(r1)
\tstw r0, 0x10(r4)
{la("r4", "lbl_1_data_C66")}\tslwi r5, r30, 1
\tlwz r0, 0x14(r1)
\tsthx r0, r4, r5
{la("r4", "lbl_1_rodata_7C")}\tlwz r0, 0x18(r1)
\tstwx r0, r4, r28
{la("r3", "lbl_1_bss_918")}\tlha r3, 0x2(r3)
\tmr r4, r30
\tlwz r5, 0x1c(r1)
\tbl {HuSprBankSet}
\taddi r30, r30, 0x1
\tcmpwi r30, {SLOTS}
\tblt .L_pg_apply_slot
\tbl fn_1_pg_refresh
\tlmw r27, 0x3c(r1)
\tlwz r0, 0x54(r1)
\tmtlr r0
\taddi r1, r1, 0x50
\tblr
.endfn fn_1_pg_apply

# The six icon models' textures from lbl_1_bss_800, as fn_1_19510 sets them (0x1955C-0x196DC)
.fn fn_1_pg_refresh, global
\tstwu r1, -0x20(r1)
\tmflr r0
\tstw r0, 0x24(r1)
\tstmw r28, 0x10(r1)
\tli r31, 0x0
.L_pg_refresh_slot:
\taddi r3, r31, 0xb
\tmulli r3, r3, 0x38
{la("r30", "lbl_1_bss_288")}\tadd r30, r30, r3
{la("r29", "lbl_1_bss_800")}\tslwi r3, r31, 2
\tadd r3, r29, r3
\tlwz r28, 0x30(r3)
\tlha r3, 0x2(r30)
\tmr r4, r28
\tbl {Hu3DAnimAnimSet}
\tlha r3, 0x4(r30)
\tmr r4, r28
\tbl {Hu3DAnimAnimSet}
\tlha r3, 0x4(r30)
\tli r4, 0x1
\tbl {Hu3DAnimBankSet}
\tlha r3, 0x6(r30)
\tmr r4, r28
\tbl {Hu3DAnimAnimSet}
\tlha r3, 0x8(r30)
\tmr r4, r28
\tbl {Hu3DAnimAnimSet}
\tlha r3, 0x8(r30)
\tli r4, 0x1
\tbl {Hu3DAnimBankSet}
{la("r3", "lbl_1_data_C66")}\tslwi r4, r31, 1
\tlhax r0, r3, r4
\tcmpwi r0, 0x0
\tbne .L_pg_refresh_next
\tlha r3, 0x6(r30)
\tlwz r4, 0xa0(r29)
\tbl {Hu3DAnimAnimSet}
\tlha r3, 0x8(r30)
\tlwz r4, 0xa0(r29)
\tbl {Hu3DAnimAnimSet}
.L_pg_refresh_next:
\taddi r31, r31, 0x1
\tcmpwi r31, {SLOTS}
\tblt .L_pg_refresh_slot
\tlmw r28, 0x10(r1)
\tlwz r0, 0x24(r1)
\tmtlr r0
\taddi r1, r1, 0x20
\tblr
.endfn fn_1_pg_refresh

# r3 = page: turn to it (saving page 0's entries when leaving page 0)
.fn fn_1_pg_go, global
{la("r4", "lbl_1_bss_pg_page")}\tlwz r5, 0x0(r4)
\tcmpw r3, r5
\tbeqlr
\tcmpwi r5, 0x0
\tbne .L_pg_go_apply
\tli r6, 0x0
{la("r7", "lbl_1_bss_pg_orig")}.L_pg_go_save:
\tslwi r8, r6, 2
{la("r9", "lbl_1_bss_800")}\tadd r9, r9, r8
\tlwz r0, 0x30(r9)
\tstwx r0, r7, r8
{la("r9", "lbl_1_rodata_7C")}\tlwzx r0, r9, r8
\taddi r10, r8, 0x{ORIG_DLL:X}
\tstwx r0, r7, r10
\tslwi r8, r6, 3
{la("r9", "lbl_1_bss_93C")}\tadd r9, r9, r8
\taddi r10, r8, 0x{ORIG_DISC:X}
\tadd r10, r7, r10
\tlwz r0, 0xc(r9)
\tstw r0, 0x0(r10)
\tlwz r0, 0x10(r9)
\tstw r0, 0x4(r10)
\tslwi r8, r6, 1
{la("r9", "lbl_1_data_C66")}\tlhzx r0, r9, r8
\taddi r10, r8, 0x{ORIG_C66:X}
\tsthx r0, r7, r10
\taddi r6, r6, 0x1
\tcmpwi r6, {SLOTS}
\tblt .L_pg_go_save
.L_pg_go_apply:
\tb fn_1_pg_apply
.endfn fn_1_pg_go

# fn_1_188BC, cursor left: the previous board, across pages
.fn fn_1_pg_left, global
\tstwu r1, -0x20(r1)
\tmflr r0
\tstw r0, 0x24(r1)
\tstmw r29, 0x14(r1)
{la("r31", "lbl_1_bss_9F4")}\tlha r30, 0x4(r31)
\tsubi r30, r30, 0x1
\tcmpwi r30, 0x0
\tbge .L_pg_left_store
\tbl fn_1_pg_pages
{la("r4", "lbl_1_bss_pg_page")}\tlwz r29, 0x0(r4)
\tadd r29, r29, r3
\tsubi r29, r29, 0x1
\tdivwu r4, r29, r3
\tmullw r4, r4, r3
\tsubf r29, r4, r29
\tmr r3, r29
\tbl fn_1_pg_count
\tsubi r30, r3, 0x1
\tmr r3, r29
\tbl fn_1_pg_go
.L_pg_left_store:
\tsth r30, 0x4(r31)
\tlmw r29, 0x14(r1)
\tlwz r0, 0x24(r1)
\tmtlr r0
\taddi r1, r1, 0x20
\tblr
.endfn fn_1_pg_left

# fn_1_188BC, cursor right: the next board, across pages
.fn fn_1_pg_right, global
\tstwu r1, -0x20(r1)
\tmflr r0
\tstw r0, 0x24(r1)
\tstmw r29, 0x14(r1)
{la("r31", "lbl_1_bss_9F4")}\tlha r30, 0x4(r31)
\taddi r30, r30, 0x1
{la("r4", "lbl_1_bss_pg_page")}\tlwz r29, 0x0(r4)
\tmr r3, r29
\tbl fn_1_pg_count
\tcmpw r30, r3
\tblt .L_pg_right_store
\tbl fn_1_pg_pages
\taddi r29, r29, 0x1
\tdivwu r4, r29, r3
\tmullw r4, r4, r3
\tsubf r29, r4, r29
\tli r30, 0x0
\tmr r3, r29
\tbl fn_1_pg_go
.L_pg_right_store:
\tsth r30, 0x4(r31)
\tlmw r29, 0x14(r1)
\tlwz r0, 0x24(r1)
\tmtlr r0
\taddi r1, r1, 0x20
\tblr
.endfn fn_1_pg_right

# fn_1_19510: the screen opens on slot 0 of page 0
.fn fn_1_pg_home, global
\tstwu r1, -0x10(r1)
\tmflr r0
\tstw r0, 0x14(r1)
\tli r0, 0x0
{la("r3", "lbl_1_bss_9F4")}\tsth r0, 0x4(r3)
\tli r3, 0x0
\tbl fn_1_pg_go
\tlwz r0, 0x14(r1)
\tmtlr r0
\taddi r1, r1, 0x10
\tblr
.endfn fn_1_pg_home

# fn_1_918: r0 = the board number to launch (r3 = lbl_1_bss_9F4, kept); for an extra board also its overlay into
# the DLL table entry its number aliases to (the launch indexes the table by the aliased board number)
.fn fn_1_pg_board_no, global
\tstwu r1, -0x20(r1)
\tstw r11, 0x8(r1)
\tstw r12, 0xc(r1)
\tmfcr r12
\tstw r12, 0x10(r1)
\tlha r0, 0x4(r3)
{la("r12", "lbl_1_bss_pg_page")}\tlwz r12, 0x0(r12)
\tcmpwi r12, 0x0
\tbeq .L_pg_board_no_done
\tsubi r12, r12, 0x1
\tmulli r12, r12, {SLOTS}
\tadd r12, r12, r0
\tmulli r12, r12, {BOARD_ROW}
{la("r11", "lbl_1_data_pg_boards")}\tadd r11, r11, r12
\tlwz r0, 0x0(r11)
\tlwz r12, 0x4(r11)
{la("r11", "lbl_1_rodata_7C")}\tstw r12, 0x{4 * ALIAS:X}(r11)
.L_pg_board_no_done:
\tlwz r12, 0x10(r1)
\tmtcr r12
\tlwz r12, 0xc(r1)
\tlwz r11, 0x8(r1)
\taddi r1, r1, 0x20
\tblr
.endfn fn_1_pg_board_no

# fn_1_305E0: the cursor (and page) from the board just played; r3 = the cursor it computed, r31 = lbl_1_bss_9F4
.fn fn_1_pg_return, global
\tstwu r1, -0x20(r1)
\tmflr r0
\tstw r0, 0x24(r1)
\tstmw r29, 0x14(r1)
\tmr r30, r3
{la("r4", GwSystem)}\tlbz r4, 0x8(r4)
\tclrlwi r4, r4, 27
{la("r5", "lbl_1_data_pg_cfg")}\tlwz r5, 0x0(r5)
{la("r6", "lbl_1_data_pg_boards")}\tli r29, 0x0
.L_pg_return_find:
\tcmpw r29, r5
\tbge .L_pg_return_mp6
\tmulli r7, r29, {BOARD_ROW}
\tlwzx r0, r6, r7
\tcmpw r0, r4
\tbeq .L_pg_return_extra
\taddi r29, r29, 0x1
\tb .L_pg_return_find
.L_pg_return_extra:
\tli r4, {SLOTS}
\tdivwu r3, r29, r4
\tmullw r4, r3, r4
\tsubf r30, r4, r29
\taddi r3, r3, 0x1
\tb .L_pg_return_go
.L_pg_return_mp6:
\tli r3, 0x0
.L_pg_return_go:
\tsth r30, 0x4(r31)
\tbl fn_1_pg_go
{la("r5", "lbl_1_data_pg_cfg")}\tlwz r5, 0x0(r5)
\tcmpw r29, r5
\tbge .L_pg_return_done
\tmulli r7, r29, {BOARD_ROW}
{la("r6", "lbl_1_data_pg_boards")}\tadd r6, r6, r7
\tlwz r0, 0x4(r6)
{la("r6", "lbl_1_rodata_7C")}\tstw r0, 0x{4 * ALIAS:X}(r6)
.L_pg_return_done:
\tlmw r29, 0x14(r1)
\tlwz r0, 0x24(r1)
\tmtlr r0
\taddi r1, r1, 0x20
\tblr
.endfn fn_1_pg_return

# fn_1_39E00: r3 = cursor -> r3 = 0x20000 + the board's index (the caller adds 9: description records)
.fn fn_1_pg_desc, global
\tstwu r1, -0x20(r1)
\tstw r12, 0x8(r1)
\tmfcr r12
\tstw r12, 0xc(r1)
{la("r12", "lbl_1_bss_pg_page")}\tlwz r12, 0x0(r12)
\tmulli r12, r12, {SLOTS}
\tadd r3, r3, r12
\taddis r3, r3, 0x2
\tlwz r12, 0xc(r1)
\tmtcr r12
\tlwz r12, 0x8(r1)
\taddi r1, r1, 0x20
\tblr
.endfn fn_1_pg_desc

# r3 = data number -> r3 = its ANIMDATA, read as fn_1_2E380 reads the menu's animations
.fn fn_1_pg_read, global
\tstwu r1, -0x10(r1)
\tmflr r0
\tstw r0, 0x14(r1)
\tlis r4, 0x1000
\tli r5, 0x2
\tbl {HuDataSelHeapReadNum}
\tbl {HuSprAnimRead}
\tlwz r0, 0x14(r1)
\tmtlr r0
\taddi r1, r1, 0x10
\tblr
.endfn fn_1_pg_read

# fn_1_2E380's last call, HuPrcChildCreate(r3-r7): first load the extra boards' animations, page 0
.fn fn_1_pg_init_child, global
\tstwu r1, -0x30(r1)
\tmflr r0
\tstw r0, 0x34(r1)
\tstw r3, 0x8(r1)
\tstw r4, 0xc(r1)
\tstw r5, 0x10(r1)
\tstw r6, 0x14(r1)
\tstw r7, 0x18(r1)
\tstmw r29, 0x20(r1)
{la("r31", "lbl_1_data_pg_cfg")}\tlwz r3, 0x4(r31)
\tbl fn_1_pg_read
{la("r4", "lbl_1_bss_pg_empty")}\tstw r3, 0x0(r4)
\tli r30, 0x0
.L_pg_init_board:
\tlwz r0, 0x0(r31)
\tcmpw r30, r0
\tbge .L_pg_init_done
\tmulli r29, r30, {BOARD_ROW}
{la("r3", "lbl_1_data_pg_boards")}\tadd r29, r3, r29
\tmulli r0, r30, {ANIM_ROW}
\tstw r0, 0x1c(r1)
\tlwz r3, 0x8(r29)
\tbl fn_1_pg_read
{la("r4", "lbl_1_bss_pg_anim")}\tlwz r0, 0x1c(r1)
\tstwx r3, r4, r0
\tlwz r3, 0xc(r29)
\tbl fn_1_pg_read
{la("r4", "lbl_1_bss_pg_anim")}\tlwz r0, 0x1c(r1)
\tadd r4, r4, r0
\tstw r3, 0x4(r4)
\tlwz r3, 0x10(r29)
\tbl fn_1_pg_read
{la("r4", "lbl_1_bss_pg_anim")}\tlwz r0, 0x1c(r1)
\tadd r4, r4, r0
\tstw r3, 0x8(r4)
\taddi r30, r30, 0x1
\tb .L_pg_init_board
.L_pg_init_done:
\tli r0, 0x0
{la("r4", "lbl_1_bss_pg_page")}\tstw r0, 0x0(r4)
\tlmw r29, 0x20(r1)
\tlwz r3, 0x8(r1)
\tlwz r4, 0xc(r1)
\tlwz r5, 0x10(r1)
\tlwz r6, 0x14(r1)
\tlwz r7, 0x18(r1)
\tbl {HuPrcChildCreate}
\tlwz r0, 0x34(r1)
\tmtlr r0
\taddi r1, r1, 0x30
\tblr
.endfn fn_1_pg_init_child
"""


def hook_text(text):
    """`text` (the vanilla listing) with HOOKS applied; raises if a site doesn't hold its vanilla word."""
    lines = text.split("\n")
    index = {}
    for i, line in enumerate(lines):
        if line.startswith("/* ") and line[11] == " ":
            index.setdefault(int(line[3:11], 16), i)
    for offset, vanilla, new in HOOKS:
        i = index.get(offset)
        if i is None:
            raise RuntimeError(f"mdpartydll .text {offset:#x} not in the listing")
        prefix, insn = lines[i].split("\t", 1)
        if vanilla is not None and insn.strip() != vanilla:
            raise RuntimeError(f"mdpartydll .text {offset:#x}: {insn.strip()!r}, expected {vanilla!r}")
        if offset in BLOCK_INNER and lines[i + 1].startswith(".L_"):
            raise RuntimeError(f"mdpartydll .text {offset:#x}: a label inside a hooked block")
        lines[i] = f"{prefix}\t{new}"
    return "\n".join(lines)


def patch_asm():
    if not ASM_PRE.exists():
        shutil.copytree(ASM, ASM_PRE)
    for src in ASM_PRE.glob("*.s"):
        shutil.copyfile(src, ASM / src.name)
    TEXT.write_text(hook_text(TEXT.read_text()).rstrip("\n") + "\n" + TEXT_CODE)
    DATA.write_text(DATA.read_text().rstrip("\n") + "\n" + data_text())
    BSS.write_text(BSS.read_text().rstrip("\n") + "\n" + bss_text())


def main():
    patch_asm()
    rel = rebuild_mdpresult.rebuild("mdpartydll")
    print(f"Built {rel}: board select pages for {len(EXTRA_BOARDS)} extra board(s) "
          f"(mdparty.bin files {MDPARTY_FILES}-{NEW_FILES - 1}, bank 2 records {DESC_FIRST}+)")


if __name__ == "__main__":
    sys.exit(main())
