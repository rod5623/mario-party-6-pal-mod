"""Duel-type (type 6) copy of Daft Rafts (m609): only the two duelists race.

Run after apply_mgtable_move_patch.py and apply_battle_ports_patch.py (it reuses the
relocated table, the caves and the instDll index limit). Edits build/GP6P01/main.dol and a
patched copy of m609dll.rel in build/GP6P01/files/dll/.

Table: entry 86 is a copy of m609's entry (index 8) with type = MG_TYPE_KETTOU (6); the 4P
entry is unchanged.

REL: the game keeps one state struct per player slot (REL bss_24C, stride 0x130, built by
fn_1_3C0 from GwPlayerConf). A slot with +0x6D != 0 is "dead": fn_1_52B8 hides its raft and
fn_1_4FC0 counts it as out (+0x1B = -1), so it is never a winner and the race can finish
with two players. The `bl fn_1_3C0` at .text 0xD27C (in fn_1_D1CC) is redirected to a cave
that, for a type-6 entry, calls fn_1_3C0 and then sets +0x6D = 1 on every slot whose
GwPlayerConf grpNo is 2 or more (the Duel space gives the two duelists grpNo 0 and 1).
Any other entry type falls straight through.
"""
from tools.lib.paths import DOL, ROOT, BUILD
from tools.lib.minigames import NEW_BASE
from tools.lib.ppc import (
    Asm, BLR, LHZ, MFLR, MTLR, LWZ, STW, STWU, ha, i_add, i_addi, i_cmpwi, i_lis, i_mem, i_slwi, lo,
)
from tools.lib.minigames import emit_type_check
from tools.lib import battle_port as bp
from tools.lib.dol import write_cave
from tools.lib.rel import add_calls, check_words

REL_DIR = BUILD / "files" / "dll"
REL_ORIG = ROOT / "orig" / "GP6P01" / "files" / "dll"
REL_NAME = "m609dll.rel"

MG_TYPE_KETTOU = 6
SRC_INDEX = 8  # m609 in the vanilla table
NEW_INDEX = 86
HOOK = NEW_BASE + 0x3100  # free tail of the relocated table section (0x802F7AA0)

GW_PLAYER_CONF = 0x80282E48
CONF_SIZE = 0xA
SLOT_SIZE = 0x130

SITE = 0xD27C  # bl fn_1_3C0 inside fn_1_D1CC; LR after the call = 0xD280
FN_1_3C0 = 0x3C0
LR_TO_FN = 0xD280 - FN_1_3C0  # fn_1_3C0 = LR - 0xCEC0
# fn_1_3C0 materialises the slot array with `lis r3, bss_24C@ha` / `addi r0, r3, bss_24C@l`
HA_INSN = 0x5D4 - FN_1_3C0
LO_INSN = 0x5D8 - FN_1_3C0

LHA, STB = 42, 38
MTCTR = lambda r: 0x7C0903A6 | (r << 21)
BCTRL = 0x4E800421


def build_hook(address):
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(11))
    a.word(i_mem(STW, 11, 1, 0x24))  # return address (REL 0xD280)
    a.word(i_addi(12, 11, -0x6000))
    a.word(i_addi(12, 12, -(LR_TO_FN - 0x6000)))  # r12 = fn_1_3C0
    a.word(i_mem(STW, 12, 1, 0x8))
    a.word(MTCTR(12))
    a.word(BCTRL)
    emit_type_check(a, 12, 11, "done", MG_TYPE_KETTOU)
    # r10 = &bss_24C (read back from the relocated lis/addi pair in fn_1_3C0)
    a.word(i_mem(LWZ, 12, 1, 0x8))
    a.word(i_mem(LHZ, 10, 12, HA_INSN + 2))
    a.word(i_slwi(10, 10, 16))
    a.word(i_mem(LHA, 11, 12, LO_INSN + 2))
    a.word(i_add(10, 10, 11))
    a.word(i_lis(9, ha(GW_PLAYER_CONF)))
    a.word(i_addi(9, 9, lo(GW_PLAYER_CONF)))
    a.word(i_addi(8, 0, 0))
    a.label("loop")
    a.word(i_mem(LHA, 0, 9, 6))  # grpNo
    a.word(i_cmpwi(0, 2))
    a.branch("blt", "next")
    a.word(i_addi(0, 0, 1))
    a.word(i_mem(STB, 0, 10, 0x6D))  # dead: hidden and counted out
    a.label("next")
    a.word(i_addi(9, 9, CONF_SIZE))
    a.word(i_addi(10, 10, SLOT_SIZE))
    a.word(i_addi(8, 8, 1))
    a.word(i_cmpwi(8, 4))
    a.branch("blt", "loop")
    a.label("done")
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(i_addi(1, 1, 0x20))
    a.word(MTLR(0))
    a.word(BLR)
    return a.assemble()


def main():
    dol = bytearray(DOL.read_bytes())
    write_cave(dol, HOOK, build_hook(HOOK))
    bp.add_table_entry(dol, SRC_INDEX, NEW_INDEX, MG_TYPE_KETTOU)
    DOL.write_bytes(dol)

    path = REL_DIR / REL_NAME
    data = bytearray((path if path.exists() else REL_ORIG / REL_NAME).read_bytes())
    check_words(data, SITE, "4BFF3145", "48000001")
    if add_calls(data, [(SITE, HOOK)]):
        REL_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"Hooked Daft Rafts ({REL_NAME})")
    else:
        print("Daft Rafts already hooked")


if __name__ == "__main__":
    main()
