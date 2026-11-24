"""Unlucky Star counter: coins + 30 x Stars lost to bad luck, in GwPlayer+0x104.

GwPlayer+0x104 is coinGraph[51], which nothing uses (resultDll writes graph[turn-1] only
while turn < 52, and the results screen reads graph[0..turnMax], turnMax <= 50). It is
reset at board start by apply_random_bonus_patch.py (stw r5,0x104 in its board-init cave),
which also adds the Unlucky Star (award 7) to the ceremony.

Every board coin and Star change ends in two setters:
  * coins: fn_8003CDA8, `sth r31,0x1c(r3)` at 0x8003CE3C  -> cave_coin
  * Stars: fn_8003CF28, `sth r4,0x30(r5)`  at 0x8003CF8C  -> cave_star (each Star = 30)
Both call unl_note, which adds any decrease to +0x104 (capped at 9999) only when it is
bad luck:
  * a red space: 0x80176AC4 `bl fn_8015EC7C` (the -3 coin space handler) -> cave_red,
    which sets unl_flag around the call;
  * or the current process (or one of its parents) is an orb/space event process from
    the slot table lbl_802DC2E0 (started by fn_801D5EB4, param block at process+0x12C:
    +0 player, +8 event id), and the event is
      10-25  hit and trap orbs (incl. the Star Trap orb 14, Thwomp's toll),
      42     Miracle space (Round of Miracles swaps),
      43     Bowser space (Bowser Bonus and the Bowser Mini-Game penalty),
      44     DK space,
      46     Boo house: only the victims count; the player who called Boo is paying.
Spending (Star/orb purchases, tolls outside those events) never counts.

Code: DOL section 17 (apply_egadd_morpher_patch.py) at CAVE.., after the E. Gadd robots.
Assembled with the bundled binutils. Run after egadd_robots (needs section 17). Idempotent.
"""
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.lib.paths import DOL
from tools.lib.dol import dol_offset, encode_branch
from tools.patches import apply_egadd_morpher_patch as morph
from tools.patches import apply_egadd_robots_patch as robots

from tools.lib.paths import ROOT
BIN = ROOT / "build/binutils"

CAVE = 0x802F9A00
CAVE_END = 0x802F9C00
assert robots.USED_END <= CAVE and CAVE_END <= morph.CODE_END

HOOK_COIN, WORD_COIN = 0x8003CE3C, 0xB3E3001C   # sth r31, 0x1c(r3)
HOOK_STAR, WORD_STAR = 0x8003CF8C, 0xB0850030   # sth r4, 0x30(r5)
HOOK_RED = 0x80176AC4                            # bl fn_8015EC7C
FN_RED = 0x8015EC7C

SYMBOLS = {
    "SLOTS": 0x802DC2E0,      # event process slots (8)
    "GWP": 0x80282E70,        # GwPlayer
    "COIN_BACK": HOOK_COIN + 4,
    "RED_FN": FN_RED,
}

SOURCE = r"""
    .text
    .globl unl_note
# r3 = &GwPlayer[p], r4 = old, r5 = new, r6 = weight. Preserves r3-r6.
unl_note:
    stwu r1, -0x20(r1)
    mflr r0
    stw r0, 0x24(r1)
    stw r3, 0x8(r1)
    stw r4, 0xc(r1)
    stw r5, 0x10(r1)
    stw r6, 0x14(r1)
    cmpw r5, r4
    bge .Lexit
    lis r7, unl_flag@ha
    lwz r0, unl_flag@l(r7)
    cmpwi r0, 0
    bne .Lcount
    lwz r7, -0x74A8(r13)        # current process (lbl_802DD958)
    li r8, 6
.Ldepth:
    cmpwi r7, 0
    beq .Lexit
    lis r9, SLOTS@ha
    addi r9, r9, SLOTS@l
    li r10, 8
    mtctr r10
.Lslot:
    lwz r11, 0(r9)
    cmplw r11, r7
    beq .Lfound
    addi r9, r9, 4
    bdnz .Lslot
    lwz r7, 0xc(r7)             # parent
    subic. r8, r8, 1
    bne .Ldepth
    b .Lexit
.Lfound:
    lwz r9, 0x12c(r7)           # event param block
    cmpwi r9, 0
    beq .Lexit
    lwz r10, 0x8(r9)            # event id
    subi r11, r10, 10
    cmplwi r11, 15
    ble .Lcount                 # 10-25 orbs
    subi r11, r10, 42
    cmplwi r11, 2
    ble .Lcount                 # 42 Miracle, 43 Bowser, 44 DK
    cmpwi r10, 46
    bne .Lexit
    lwz r11, 0x0(r9)            # Boo: skip the player who called Boo (paying)
    lis r12, GWP@ha
    addi r12, r12, GWP@l
    subf r12, r12, r3
    li r0, 0x108
    divwu r12, r12, r0
    cmpw r12, r11
    beq .Lexit
.Lcount:
    subf r7, r5, r4
    mullw r7, r7, r6
    lha r8, 0x104(r3)
    add r8, r8, r7
    cmpwi r8, 9999
    ble .Lstore
    li r8, 9999
.Lstore:
    sth r8, 0x104(r3)
.Lexit:
    lwz r3, 0x8(r1)
    lwz r4, 0xc(r1)
    lwz r5, 0x10(r1)
    lwz r6, 0x14(r1)
    lwz r0, 0x24(r1)
    mtlr r0
    addi r1, r1, 0x20
    blr

    .globl cave_coin
# fn_8003CDA8 (frame saved LR; r3-r12 dead after the store)
cave_coin:
    lha r4, 0x1c(r3)
    extsh r5, r31
    li r6, 1
    bl unl_note
    sth r31, 0x1c(r3)
    b COIN_BACK

    .globl cave_star
# fn_8003CF28 is a leaf: keep LR; the replaced store is followed by blr
cave_star:
    mflr r0
    stwu r1, -0x10(r1)
    stw r0, 0x14(r1)
    stw r4, 0x8(r1)
    stw r5, 0xc(r1)
    mr r3, r5
    extsh r5, r4
    lha r4, 0x30(r3)
    li r6, 30
    bl unl_note
    lwz r4, 0x8(r1)
    lwz r5, 0xc(r1)
    sth r4, 0x30(r5)
    lwz r0, 0x14(r1)
    mtlr r0
    addi r1, r1, 0x10
    blr

    .globl cave_red
cave_red:
    stwu r1, -0x10(r1)
    mflr r0
    stw r0, 0x14(r1)
    lis r4, unl_flag@ha
    li r0, 1
    stw r0, unl_flag@l(r4)
    bl RED_FN
    lis r4, unl_flag@ha
    li r0, 0
    stw r0, unl_flag@l(r4)
    lwz r0, 0x14(r1)
    mtlr r0
    addi r1, r1, 0x10
    blr

    .balign 4
    .globl unl_flag
unl_flag:
    .4byte 0
"""


def assemble():
    """Assemble SOURCE at CAVE; returns (code bytes, {symbol: address})."""
    from tools.lib import rebuild_mdpresult
    rebuild_mdpresult.ensure_binutils()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "unl.s").write_text(SOURCE)
        subprocess.run([BIN / "powerpc-eabi-as.exe", "-mgekko", "-mregnames", "-o", tmp / "unl.o", tmp / "unl.s"], check=True)
        defsyms = [f"--defsym={k}=0x{v:08X}" for k, v in SYMBOLS.items()]
        subprocess.run([BIN / "powerpc-eabi-ld.exe", f"-Ttext=0x{CAVE:08X}", "-e", "unl_note",
                        *defsyms, "-o", tmp / "unl.elf", tmp / "unl.o"], check=True)
        subprocess.run([BIN / "powerpc-eabi-objcopy.exe", "-O", "binary", "-j", ".text",
                        tmp / "unl.elf", tmp / "unl.bin"], check=True)
        nm = subprocess.run([BIN / "powerpc-eabi-nm.exe", tmp / "unl.elf"], check=True,
                            capture_output=True, text=True).stdout
        code = (tmp / "unl.bin").read_bytes()
    syms = {}
    for line in nm.splitlines():
        parts = line.split()
        if len(parts) == 3:
            syms[parts[2]] = int(parts[0], 16)
    return code, syms


def main():
    code, syms = assemble()
    if CAVE + len(code) > CAVE_END:
        raise SystemExit(f"Unlucky code is {len(code):#x} bytes, room for {CAVE_END - CAVE:#x}")
    dol = bytearray(DOL.read_bytes())
    if struct.unpack_from(">I", dol, 0x48 + 4 * morph.SECTION)[0] != morph.CODE_BASE:
        raise SystemExit("DOL section 17 is missing: run apply_egadd_morpher_patch.py first")

    hooks = (
        (HOOK_COIN, WORD_COIN, encode_branch(HOOK_COIN, syms["cave_coin"])),
        (HOOK_STAR, WORD_STAR, encode_branch(HOOK_STAR, syms["cave_star"])),
        (HOOK_RED, encode_branch(HOOK_RED, FN_RED, link=True),
         encode_branch(HOOK_RED, syms["cave_red"], link=True)),
    )
    for address, original, hooked in hooks:
        current = struct.unpack_from(">I", dol, dol_offset(dol, address))[0]
        if current not in (original, hooked):
            raise SystemExit(f"Unexpected word at {address:#x}: {current:#010x}")

    at = dol_offset(dol, CAVE)
    region = bytes(dol[at:at + CAVE_END - CAVE])
    padded = code.ljust(CAVE_END - CAVE, b"\0")
    if any(region) and region != padded:
        # Accept an earlier version of this code (it starts with the same prologue)
        if region[:4] != code[:4]:
            raise SystemExit(f"{CAVE:#x}-{CAVE_END:#x} is not free")
    dol[at:at + CAVE_END - CAVE] = padded
    for address, _, hooked in hooks:
        struct.pack_into(">I", dol, dol_offset(dol, address), hooked)
    DOL.write_bytes(dol)
    print(f"Unlucky counter: {len(code):#x} bytes at {CAVE:#x}; hooks at "
          f"{HOOK_COIN:#x}, {HOOK_STAR:#x}, {HOOK_RED:#x}")


if __name__ == "__main__":
    sys.exit(main())
