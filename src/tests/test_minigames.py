"""tools.lib.minigames: the relocated MgDataTbl and emit_type_check."""
import struct

from tools.lib import minigames
from tools.lib.game import GW_SYSTEM
from tools.lib.minigames import ENTRY_SIZE, NEW_BASE, NEW_END, NEW_SIZE, SECTION_SLOT, emit_type_check
from tools.lib.ppc import Asm, ha, lo


def assembled():
    a = Asm(0x80300000)
    emit_type_check(a, 3, 4, "not_battle")
    a.word(0x60000000)
    a.label("not_battle")
    return list(struct.unpack(">10I", a.assemble()))


def test_type_check_words():
    words = assembled()
    lis, addi = words[3], words[4]
    assert lis >> 26 == 15 and (lis >> 21) & 31 == 4 and lis & 0xFFFF == ha(NEW_BASE)
    assert addi >> 26 == 14 and (addi >> 16) & 31 == 4 and addi & 0xFFFF == lo(NEW_BASE)
    assert words[0] & 0xFFFF == ha(GW_SYSTEM + 0x38)
    assert words[2] & 0xFFFF == ENTRY_SIZE                  # mulli by the entry size
    assert words[6] >> 26 == 34 and words[6] & 0xFFFF == 2  # lbz type at +2
    assert words[7] >> 26 == 10 and words[7] & 0xFFFF == minigames.MG_TYPE_BATTLE


def test_type_check_ends_in_bne_to_label():
    bne = assembled()[8]
    assert bne >> 26 == 16 and (bne >> 21) & 31 == 4 and (bne >> 16) & 31 == 2
    assert bne & 0xFFFC == 8                                # skips the nop to the label


def test_table_constants():
    assert NEW_END == NEW_BASE + NEW_SIZE
    assert SECTION_SLOT == 15


def test_table_capacity_below_section15_caves():
    # patching-guide.md section 8: the first section-15 cave is at NEW_BASE + 0x2F00, so the
    # table holds at most 97 slots (indices 0-95 plus the terminator).
    first_cave = 0x2F00
    assert 97 * ENTRY_SIZE == 0x2EFC <= first_cave
    assert 98 * ENTRY_SIZE > first_cave
