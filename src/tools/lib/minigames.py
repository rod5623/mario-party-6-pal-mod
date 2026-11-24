"""The minigame table (MgDataTbl) and where apply_mgtable_move_patch.py relocates it."""
from tools.lib.game import GW_SYSTEM
from tools.lib.ppc import LBZ, LHZ, ha, i_add, i_addi, i_cmplwi, i_lis, i_mem, i_mulli, lo

MG_TYPE_BATTLE = 3


def emit_type_check(a, reg_a, reg_b, not_battle_label, mg_type=MG_TYPE_BATTLE):
    """cmplwi MgDataTbl[GwSystem.mgNo].type, mg_type; bne not_battle_label (clobbers reg_a, reg_b)."""
    a.word(i_lis(reg_a, ha(GW_SYSTEM + 0x38)))
    a.word(i_mem(LHZ, reg_a, reg_a, lo(GW_SYSTEM + 0x38)))
    a.word(i_mulli(reg_a, reg_a, ENTRY_SIZE))
    a.word(i_lis(reg_b, ha(NEW_BASE)))
    a.word(i_addi(reg_b, reg_b, lo(NEW_BASE)))
    a.word(i_add(reg_a, reg_a, reg_b))
    a.word(i_mem(LBZ, reg_a, reg_a, 2))
    a.word(i_cmplwi(reg_a, mg_type))
    a.branch("bne", not_battle_label)

OLD_BASE = 0x8022FF44

ENTRY_SIZE = 0x7C

NEW_BASE = 0x802F49A0  # vanilla __ArenaLo (see ldscript.lcf)

NEW_SIZE = 0x3400  # room for 105 entries (82 now)

NEW_END = NEW_BASE + NEW_SIZE

SECTION_SLOT = 15  # first unused DOL data section slot
