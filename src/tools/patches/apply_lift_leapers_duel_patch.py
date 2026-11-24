"""Duel-type (type 6) copy of Lift Leapers (m618): only the two duelists play.

Run after apply_mgtable_move_patch.py and apply_battle_ports_patch.py (and after
apply_daft_rafts_duel_patch.py, which owns table entry 86). Edits build/GP6P01/main.dol and a
patched copy of m618dll.rel in build/GP6P01/files/dll/.

Table: entry 87 is a copy of m618's entry (index 17) with type = MG_TYPE_KETTOU (6).

REL: all four players are still created and all four viewports are still drawn, but the two
non-duelists are frozen. fn_1_214C runs the per-player update (AI, state handlers, finish
test) in a `for (i = 0; i < 4; i++)` loop whose body starts at .text 0x2184
(`mulli r4, r31, 0x68`). That instruction is replaced by a `bl` to a cave. For a type-6 entry,
if GwPlayerConf[i].grpNo >= 2 the cave returns to 0x31A0 (the `i++` of the loop), so the
player is never updated and can never finish or be picked as the winner. Otherwise it runs
the displaced instruction and returns. Other entry types are unaffected.

The viewport layout is not changed (a non-duelist keeps its quadrant, standing still).
"""
from tools.lib.paths import DOL, ROOT, BUILD
from tools.lib.minigames import NEW_BASE
from tools.lib.ppc import Asm, BLR, MFLR, MTLR, ha, i_add, i_addi, i_cmpwi, i_lis, i_mem, i_mulli, lo
from tools.lib.minigames import emit_type_check
from tools.lib import battle_port as bp
from tools.lib.dol import write_cave
from tools.lib.rel import add_calls, check_words

REL_DIR = BUILD / "files" / "dll"
REL_ORIG = ROOT / "orig" / "GP6P01" / "files" / "dll"
REL_NAME = "m618dll.rel"

MG_TYPE_KETTOU = 6
SRC_INDEX = 17  # m618 in the vanilla table
NEW_INDEX = 87
HOOK = NEW_BASE + 0x3200  # free tail of the relocated table section (0x802F7BA0)

GW_PLAYER_CONF = 0x80282E48
CONF_SIZE = 0xA

SITE = 0x2184  # mulli r4, r31, 0x68: first instruction of the fn_1_214C player loop body
SITE_WORD = "1C9F0068"
SKIP = 0x31A0 - 0x2188  # loop increment, relative to the LR set by the bl at SITE
LHA = 42


def build_hook(address):
    a = Asm(address)
    emit_type_check(a, 12, 11, "normal", MG_TYPE_KETTOU)
    a.word(i_lis(12, ha(GW_PLAYER_CONF)))
    a.word(i_addi(12, 12, lo(GW_PLAYER_CONF)))
    a.word(i_mulli(11, 31, CONF_SIZE))
    a.word(i_add(12, 12, 11))
    a.word(i_mem(LHA, 11, 12, 6))  # grpNo
    a.word(i_cmpwi(11, 2))
    a.branch("blt", "normal")
    a.word(MFLR(12))
    a.word(i_addi(12, 12, SKIP))
    a.word(MTLR(12))
    a.word(BLR)
    a.label("normal")
    a.word(i_mulli(4, 31, 0x68))
    a.word(BLR)
    return a.assemble()


def main():
    dol = bytearray(DOL.read_bytes())
    write_cave(dol, HOOK, build_hook(HOOK))
    bp.add_table_entry(dol, SRC_INDEX, NEW_INDEX, MG_TYPE_KETTOU)
    DOL.write_bytes(dol)

    path = REL_DIR / REL_NAME
    data = bytearray((path if path.exists() else REL_ORIG / REL_NAME).read_bytes())
    check_words(data, SITE, SITE_WORD, "48000001")
    if add_calls(data, [(SITE, HOOK)]):
        REL_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"Hooked Lift Leapers ({REL_NAME})")
    else:
        print("Lift Leapers already hooked")


if __name__ == "__main__":
    main()
