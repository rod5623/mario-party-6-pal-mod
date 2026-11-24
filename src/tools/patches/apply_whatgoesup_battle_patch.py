"""Add a Battle-type copy of What Goes Up (m604) to the minigame table.

Requires apply_mgtable_move_patch.py to have run first (the table must live in
the relocated DOL section). The original 4P entry is untouched; the new entry
(table index 82) shares the same overlay, with type MG_TYPE_BATTLE.

The REL is not modified in its code, only hooked. Two relocations are added to
build/GP6P01/files/dll/m604DLL.rel so that two spots in fn_1_6AE4 call DOL code:
  0x6D0C  lwz r0,0x374(r31)  -> bl hook_a: for a type-3 entry, take the
          "decathlon" path so fn_1_7534 copies every player's score into
          GwPlayer[i].mgScore (+0x2C). No winner banner or "+0x28 = 10".
  0x6D80  bl fn_1_1914C      -> bl hook_b: for a type-3 entry (and not
          practice), dense-rank those scores into GwPlayer[i].mgCoinBonus
          (+0x28, 0 = best) as Battle minigames do, then jump on to
          fn_1_1914C. Day: higher height wins. Night: lower wins.
"""
import struct

from tools.lib.paths import BUILD, DOL
from tools.lib.dol import dol_offset
from tools.lib.minigames import ENTRY_SIZE, NEW_BASE
from tools.lib.ppc import (
    Asm, ha, lo, i_addi, i_lis, i_ori, i_mem, LWZ, STW, STH, STWU, i_add, i_lwzx, i_cmpw, i_cmpwi,
    i_mulli, i_slwi, i_clrlwi24, MFLR, MTLR, MTCTR, BCTR, BLR,
)
from tools.lib.rel import R_PPC_REL24, R_DOLPHIN_SECTION, R_DOLPHIN_END
from tools.lib.game import FN_PRACTICE_CHECK, GW_PLAYER, PLAYER_SIZE
from tools.lib.minigames import MG_TYPE_BATTLE, emit_type_check

REL = BUILD / "files" / "dll" / "m604DLL.rel"

SRC_INDEX = 3  # m604 in the vanilla table
NEW_INDEX = 82  # first free slot (the terminator moves to 83)

HOOK_A = 0x80004D40
HOOK_B = 0x80004D80

TEXT_FILE_OFFSET = 0xD4  # REL section 1 (.text)
SITE_A = 0x6D0C
SITE_B = 0x6D80
SITE_A_OLD = bytes.fromhex("801F0374")  # lwz r0,0x374(r31)
SITE_A_NEW = bytes.fromhex("48000001")  # bl (displacement filled by the relocation)
SITE_B_OLD = bytes.fromhex("480123CD")  # bl fn_1_1914C
TARGET_FROM_LR = 0x123C8  # fn_1_1914C = (LR after the bl at SITE_B) + this


def build_hook_a():
    a = Asm(HOOK_A)
    a.word(i_mem(LWZ, 0, 31, 0x374))
    a.word(i_cmpwi(0, 0))
    a.branch("bne", "ret")
    emit_type_check(a, 12, 11, "ret")
    a.word(i_addi(0, 0, 1))
    a.label("ret")
    a.word(BLR)
    return a.assemble()


def build_hook_b():
    a = Asm(HOOK_B)
    a.word(i_mem(STWU, 1, 1, -0x40))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x44))
    emit_type_check(a, 3, 4, "done")
    # practice minigames pay nothing, so leave the scores alone
    a.word(i_lis(3, 1))
    a.word(i_ori(3, 3, 0xF))
    a.call(FN_PRACTICE_CHECK)
    a.word(i_clrlwi24(3, 3))
    a.word(i_cmpwi(3, 0))
    a.branch("bne", "done")
    # decathlon flag: keep mgScore only there
    a.word(i_lis(3, 3))
    a.word(i_ori(3, 3, 2))
    a.call(FN_PRACTICE_CHECK)
    a.word(i_clrlwi24(3, 3))
    a.word(i_mem(STW, 3, 1, 0x8))
    # scores -> stack[0x10..0x1C]; r5 = GwPlayer base; r12 = night flag
    a.word(i_lis(5, ha(GW_PLAYER)))
    a.word(i_addi(5, 5, lo(GW_PLAYER)))
    for i in range(4):
        a.word(i_mem(LWZ, 6, 5, 0x2C + i * PLAYER_SIZE))
        a.word(i_mem(STW, 6, 1, 0x10 + 4 * i))
    a.word(i_mem(LWZ, 12, 31, 0x360))
    a.word(i_addi(8, 0, 0))  # i = 0
    a.label("loop_i")
    a.word(i_slwi(9, 8, 2))
    a.word(i_addi(10, 1, 0x10))
    a.word(i_lwzx(6, 10, 9))  # s_i
    a.word(i_addi(7, 0, 0))  # rank = 0
    a.word(i_addi(9, 0, 0))  # j = 0
    a.label("loop_j")
    a.word(i_slwi(10, 9, 2))
    a.word(i_addi(11, 1, 0x10))
    a.word(i_lwzx(10, 11, 10))  # s_j
    a.word(i_cmpw(10, 6))
    a.word(i_cmpwi(12, 0))
    a.branch("bne", "night")
    a.word(i_cmpw(10, 6))
    a.branch("ble", "next_j")  # day: needs s_j > s_i
    a.branch("b", "better")
    a.label("night")
    a.word(i_cmpw(10, 6))
    a.branch("bge", "next_j")  # night: needs s_j < s_i
    a.label("better")
    a.word(i_addi(11, 0, 0))  # k = 0: count a value once, at its first slot
    a.label("loop_k")
    a.word(i_cmpw(11, 9))
    a.branch("bge", "first")
    a.word(i_slwi(0, 11, 2))
    a.word(i_addi(3, 1, 0x10))
    a.word(i_lwzx(0, 3, 0))
    a.word(i_cmpw(0, 10))
    a.branch("beq", "next_j")
    a.word(i_addi(11, 11, 1))
    a.branch("b", "loop_k")
    a.label("first")
    a.word(i_addi(7, 7, 1))
    a.label("next_j")
    a.word(i_addi(9, 9, 1))
    a.word(i_cmpwi(9, 4))
    a.branch("blt", "loop_j")
    a.word(i_mulli(9, 8, PLAYER_SIZE))
    a.word(i_add(9, 9, 5))
    a.word(i_mem(STH, 7, 9, 0x28))  # rank (0 = best)
    a.word(i_mem(LWZ, 0, 1, 0x8))
    a.word(i_cmpwi(0, 0))
    a.branch("bne", "keep")
    a.word(i_addi(0, 0, 0))
    a.word(i_mem(STW, 0, 9, 0x2C))
    a.label("keep")
    a.word(i_addi(8, 8, 1))
    a.word(i_cmpwi(8, 4))
    a.branch("blt", "loop_i")
    a.label("done")
    a.word(i_mem(LWZ, 0, 1, 0x44))
    a.word(i_addi(1, 1, 0x40))
    a.word(i_lis(12, TARGET_FROM_LR >> 16))
    a.word(i_ori(12, 12, TARGET_FROM_LR & 0xFFFF))
    a.word(i_add(12, 0, 12))  # fn_1_1914C
    a.word(MTCTR(12))
    a.word(MTLR(0))
    a.word(BCTR)
    return a.assemble()


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    table = dol_offset(dol, NEW_BASE)
    new_entry = table + NEW_INDEX * ENTRY_SIZE
    src_entry = table + SRC_INDEX * ENTRY_SIZE
    if struct.unpack_from(">H", dol, src_entry)[0] == 0xFFFF:
        raise RuntimeError("Source entry is a terminator; is the table the relocated one?")
    existing = struct.unpack_from(">H", dol, new_entry)[0]
    if existing == 0xFFFF:
        terminator = bytes(dol[new_entry:new_entry + ENTRY_SIZE])
        entry = bytearray(dol[src_entry:src_entry + ENTRY_SIZE])
        entry[2] = MG_TYPE_BATTLE
        dol[new_entry:new_entry + ENTRY_SIZE] = entry
        dol[new_entry + ENTRY_SIZE:new_entry + 2 * ENTRY_SIZE] = terminator
        print(f"Added table entry {NEW_INDEX} (m604, type {MG_TYPE_BATTLE}) at {NEW_BASE + NEW_INDEX * ENTRY_SIZE:#010x}")
    else:
        if dol[new_entry + 2] != MG_TYPE_BATTLE or existing != struct.unpack_from(">H", dol, src_entry)[0]:
            raise RuntimeError(f"Table slot {NEW_INDEX} is already in use by something else")
        print("Table entry already present")

    for address, code in ((HOOK_A, build_hook_a()), (HOOK_B, build_hook_b())):
        position = dol_offset(dol, address)
        current = bytes(dol[position:position + len(code)])
        if current not in (b"\0" * len(code), code):
            raise RuntimeError(f"Code cave {address:#010x} is not free")
        dol[position:position + len(code)] = code
        print(f"Wrote {len(code)} bytes at {address:#010x}")
    DOL.write_bytes(dol)


def patch_rel():
    rel = bytearray(REL.read_bytes())
    # relocation record: u16 delta, u8 type, u8 section, u32 addend
    if struct.unpack_from(">HBBI", rel, len(rel) - 8)[1] != R_DOLPHIN_END:
        raise RuntimeError("m604 REL does not end with an END relocation")
    site_a = TEXT_FILE_OFFSET + SITE_A
    site_b = TEXT_FILE_OFFSET + SITE_B
    already = rel[site_a:site_a + 4] == SITE_A_NEW
    if already:
        print("m604 REL already hooked")
        return
    if rel[site_a:site_a + 4] != SITE_A_OLD or rel[site_b:site_b + 4] != SITE_B_OLD:
        raise RuntimeError("Unexpected instructions at the m604 hook sites")
    rel[site_a:site_a + 4] = SITE_A_NEW
    records = struct.pack(">HBBI", 0, R_DOLPHIN_SECTION, 1, 0)
    records += struct.pack(">HBBI", SITE_A, R_PPC_REL24, 4, HOOK_A)
    records += struct.pack(">HBBI", SITE_B - SITE_A, R_PPC_REL24, 4, HOOK_B)
    rel[len(rel) - 8:len(rel) - 8] = records
    REL.write_bytes(rel)
    print("Added 2 module-0 relocations to m604DLL.rel")


def main():
    patch_dol()
    patch_rel()


if __name__ == "__main__":
    main()
