"""Shared pieces for porting 4P minigames into the Battle (type 3) pool.

Each ported game gets its own entry in the relocated MgDataTbl (see
apply_mgtable_move_patch.py), a copy of the 4P entry with type = 3. The REL is
then hooked (module-0 relocations to DOL code) so that, for a type-3 entry:
  * the game's own decathlon branch runs (it stores every player's score in
    GwPlayer[i]+0x2C and skips the winner banner / "+0x28 = 10" writes), and
  * rank_core() turns those scores into dense Battle ranks in GwPlayer[i]+0x28.
For the normal 4P entry the hooks fall straight through to the original code.

DOL caves (zero padding in the init section): see CAVE_* below.
"""
import struct

from tools.lib.dol import dol_offset, encode_branch
from tools.lib.minigames import ENTRY_SIZE, NEW_BASE
from tools.lib.ppc import (
    Asm, BLR, MFLR, MTLR, LHZ, LWZ, STH, STW, STWU, ha, i_add, i_addi, i_clrlwi24, i_cmpw, i_cmpwi,
    i_lis, i_lwzx, i_mem, i_mulli, i_ori, i_slwi, lo,
)
from tools.lib.game import GW_PLAYER, PLAYER_SIZE, FN_PRACTICE_CHECK
from tools.lib.minigames import MG_TYPE_BATTLE, emit_type_check
from tools.lib.dol import write_cave


CAVE_CORE = 0x80004F00  # rank_core
CAVE_FORCE = 0x80005060  # force_deca (tail-calls fn_8006A7B0)
CAVE_WRAPPERS = 0x800050A0  # per-game wrappers, 0x40 apart

NIGHT_FLAG = 0x802DDB58  # lha: 1 at night (copied from the board time of day)


def build_core():
    """rank_core(r3 = 0 higher is better, 1 lower is better).

    If MgDataTbl[GwSystem.mgNo].type == 3 and this is not a practice game,
    dense-rank GwPlayer[i]+0x2C into GwPlayer[i]+0x28 (0 = best, ties share),
    then clear +0x2C unless this is a real decathlon.
    Clobbers r0, r3-r12 only.
    """
    a = Asm(CAVE_CORE)
    a.word(i_mem(STWU, 1, 1, -0x40))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x44))
    a.word(i_mem(STW, 3, 1, 0xC))  # direction
    emit_type_check(a, 3, 4, "done")
    a.word(i_lis(3, 1))
    a.word(i_ori(3, 3, 0xF))
    a.call(FN_PRACTICE_CHECK)
    a.word(i_clrlwi24(3, 3))
    a.word(i_cmpwi(3, 0))
    a.branch("bne", "done")
    a.word(i_lis(3, 3))
    a.word(i_ori(3, 3, 2))
    a.call(FN_PRACTICE_CHECK)
    a.word(i_clrlwi24(3, 3))
    a.word(i_mem(STW, 3, 1, 0x8))
    a.word(i_lis(5, ha(GW_PLAYER)))
    a.word(i_addi(5, 5, lo(GW_PLAYER)))
    for i in range(4):
        a.word(i_mem(LWZ, 6, 5, 0x2C + i * PLAYER_SIZE))
        a.word(i_mem(STW, 6, 1, 0x10 + 4 * i))
    a.word(i_mem(LWZ, 12, 1, 0xC))
    a.word(i_addi(8, 0, 0))
    a.label("loop_i")
    a.word(i_slwi(9, 8, 2))
    a.word(i_addi(10, 1, 0x10))
    a.word(i_lwzx(6, 10, 9))
    a.word(i_addi(7, 0, 0))
    a.word(i_addi(9, 0, 0))
    a.label("loop_j")
    a.word(i_slwi(10, 9, 2))
    a.word(i_addi(11, 1, 0x10))
    a.word(i_lwzx(10, 11, 10))
    a.word(i_cmpwi(12, 0))
    a.branch("bne", "lower")
    a.word(i_cmpw(10, 6))
    a.branch("ble", "next_j")
    a.branch("b", "better")
    a.label("lower")
    a.word(i_cmpw(10, 6))
    a.branch("bge", "next_j")
    a.label("better")
    a.word(i_addi(11, 0, 0))
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
    a.word(i_mem(STH, 7, 9, 0x28))
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
    a.word(MTLR(0))
    a.word(BLR)
    return a.assemble()


def build_force():
    """force_deca: replaces the 'bl fn_8006A7B0' that tests for decathlon.

    Returns 1 for a type-3 entry; otherwise tail-calls the real fn_8006A7B0
    with the caller's r3 untouched.
    """
    a = Asm(CAVE_FORCE)
    emit_type_check(a, 12, 11, "real")
    a.word(i_addi(3, 0, 1))
    a.word(BLR)
    a.label("real")
    a.word(0)  # placeholder for the tail branch, filled in below
    code = a.assemble()
    words = list(struct.unpack(">%dI" % (len(code) // 4), code))
    tail_address = a.base + 4 * (len(words) - 1)
    words[-1] = encode_branch(tail_address, FN_PRACTICE_CHECK)
    return struct.pack(">%dI" % len(words), *words)


def build_wrapper(address, direction, replaced_words):
    """Per-game wrapper: rank_core(direction), then the instruction(s) the hook displaced.

    direction: 0 higher is better, 1 lower is better, 'night' = 1 at night, else 0.
    replaced_words: instruction words to execute after ranking (they must only use
    r0, r3-r12 or callee-saved registers the caller set up).
    """
    a = Asm(address)
    a.word(i_mem(STWU, 1, 1, -0x10))
    a.word(MFLR(12))
    a.word(i_mem(STW, 12, 1, 0x14))
    if direction == "night":
        a.word(i_lis(3, ha(NIGHT_FLAG)))
        a.word(i_mem(LHZ, 3, 3, lo(NIGHT_FLAG)))
    else:
        a.word(i_addi(3, 0, direction))
    a.call(CAVE_CORE)
    for word in replaced_words:
        a.word(word)
    a.word(i_mem(LWZ, 12, 1, 0x14))
    a.word(MTLR(12))
    a.word(i_addi(1, 1, 0x10))
    a.word(BLR)
    return a.assemble()


def build_workstruct_hook(address, ptr_array_off, idx_off, cnt_off, original_target):
    """Hook for a `bl original_target` whose caller keeps 4 work-struct pointers at ptr_array_off(r1).

    Type 3 entry: copy each player's count (work+cnt_off) into GwPlayer[work+idx_off].mgScore (+0x2C),
    run rank_core(higher is better) and return without calling original_target (no winner banner).
    Any other type: tail-call original_target with r3-r6 untouched.
    """
    a = Asm(address)
    emit_type_check(a, 12, 11, "orig")
    a.word(i_lis(5, ha(GW_PLAYER)))
    a.word(i_addi(5, 5, lo(GW_PLAYER)))
    for i in range(4):
        a.word(i_mem(LWZ, 6, 1, ptr_array_off + 4 * i))
        a.word(i_mem(LWZ, 7, 6, idx_off))
        a.word(i_mem(LWZ, 8, 6, cnt_off))
        a.word(i_mulli(7, 7, PLAYER_SIZE))
        a.word(i_add(7, 7, 5))
        a.word(i_mem(STW, 8, 7, 0x2C))
    a.word(i_mem(STWU, 1, 1, -0x10))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x14))
    a.word(i_addi(3, 0, 0))
    a.call(CAVE_CORE)
    a.word(i_mem(LWZ, 0, 1, 0x14))
    a.word(i_addi(1, 1, 0x10))
    a.word(MTLR(0))
    a.word(BLR)
    a.label("orig")
    a.word(0)  # tail branch, filled in below
    code = a.assemble()
    words = list(struct.unpack(">%dI" % (len(code) // 4), code))
    words[-1] = encode_branch(address + 4 * (len(words) - 1), original_target)
    return struct.pack(">%dI" % len(words), *words)


def build_object_hook(address, obj_reg, base_off, stride, original_target):
    """Hook for a `bl original_target` where callee-saved obj_reg points at a score object.

    Type 3 entry: copy score i (obj+base_off+i*stride) to GwPlayer[i]+0x2C, run
    rank_core(higher is better), restore r3-r5 and tail-call original_target.
    Other types: tail-call original_target untouched.
    """
    a = Asm(address)
    emit_type_check(a, 12, 11, "orig")
    a.word(i_mem(STWU, 1, 1, -0x20))
    a.word(MFLR(0))
    a.word(i_mem(STW, 0, 1, 0x24))
    a.word(i_mem(STW, 3, 1, 0x8))
    a.word(i_mem(STW, 4, 1, 0xC))
    a.word(i_mem(STW, 5, 1, 0x10))
    a.word(i_lis(5, ha(GW_PLAYER)))
    a.word(i_addi(5, 5, lo(GW_PLAYER)))
    for i in range(4):
        a.word(i_mem(LWZ, 6, obj_reg, base_off + stride * i))
        a.word(i_mem(STW, 6, 5, 0x2C + i * PLAYER_SIZE))
    a.word(i_addi(3, 0, 0))
    a.call(CAVE_CORE)
    a.word(i_mem(LWZ, 3, 1, 0x8))
    a.word(i_mem(LWZ, 4, 1, 0xC))
    a.word(i_mem(LWZ, 5, 1, 0x10))
    a.word(i_mem(LWZ, 0, 1, 0x24))
    a.word(i_addi(1, 1, 0x20))
    a.word(MTLR(0))
    a.label("orig")
    a.word(0)  # tail branch, filled in below
    code = a.assemble()
    words = list(struct.unpack(">%dI" % (len(code) // 4), code))
    words[-1] = encode_branch(address + 4 * (len(words) - 1), original_target)
    return struct.pack(">%dI" % len(words), *words)


def install_core(dol):
    write_cave(dol, CAVE_CORE, build_core())
    write_cave(dol, CAVE_FORCE, build_force())


def add_table_entry(dol, src_index, new_index, mg_type=MG_TYPE_BATTLE):
    table = dol_offset(dol, NEW_BASE)
    new_entry = table + new_index * ENTRY_SIZE
    src_entry = table + src_index * ENTRY_SIZE
    ovl = struct.unpack_from(">H", dol, src_entry)[0]
    if ovl == 0xFFFF:
        raise RuntimeError("Source entry is a terminator")
    existing = struct.unpack_from(">H", dol, new_entry)[0]
    if existing == 0xFFFF:
        terminator = bytes(dol[new_entry:new_entry + ENTRY_SIZE])
        entry = bytearray(dol[src_entry:src_entry + ENTRY_SIZE])
        entry[2] = mg_type
        dol[new_entry:new_entry + ENTRY_SIZE] = entry
        dol[new_entry + ENTRY_SIZE:new_entry + 2 * ENTRY_SIZE] = terminator
        print(f"Added table entry {new_index} (ovl {ovl:#06x}, type {mg_type})")
    elif existing != ovl or dol[new_entry + 2] != mg_type:
        raise RuntimeError(f"Table slot {new_index} is already used by something else")
    else:
        print(f"Table entry {new_index} already present")


# ---- REL relocation editing -------------------------------------------------


