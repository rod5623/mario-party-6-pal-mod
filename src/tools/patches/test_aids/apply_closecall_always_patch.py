"""Testing aid: every 4P minigame launched from a board is Close Call (table entry 88).

The minigame launcher fn_801F5854(r3 = type, r4 = table index) stores the index in GwSystem.mgNo and starts the
overlay. Its first instruction becomes a branch to a cave that sets r4 = 88 when r3 == 0 (4P), runs the
original first instruction and branches back. The roulette still shows the games it picked; Close Call is the
one that starts. 1v3, 2v2, Battle, Duel and the rest are not affected.

    python -m tools.patches.test_aids.apply_closecall_always_patch        # on
    python -m tools.patches.test_aids.apply_closecall_always_patch --off  # restore the launcher (the cave is cleared)

Run after apply_closecall_patch.py. Cave: 0x800051B4-0x800051C8 (the last free init-section padding, see
plans/minigame-pools/README.md). Edits build/GP6P01/main.dol only.
"""
import struct
import sys

from tools.lib.paths import DOL
from tools.lib.dol import dol_offset, encode_branch
from tools.patches.apply_closecall_patch import NEW_INDEX

LAUNCHER = 0x801F5854
ORIGINAL_FIRST = bytes.fromhex("9421FFD0")  # stwu r1, -0x30(r1)
CAVE = 0x800051B4


def cave_code():
    words = [
        0x2C030000,                       # cmpwi r3, 0
        0x40820008,                       # bne +8
        0x38800000 | NEW_INDEX,           # li r4, NEW_INDEX
        struct.unpack(">I", ORIGINAL_FIRST)[0],
        None,                             # b LAUNCHER + 4
    ]
    words[4] = encode_branch(CAVE + 16, LAUNCHER + 4)
    return struct.pack(">5I", *words)


def main():
    off = "--off" in sys.argv[1:]
    dol = bytearray(DOL.read_bytes())
    code = cave_code()
    cave = dol_offset(dol, CAVE)
    hook = dol_offset(dol, LAUNCHER)
    current_cave = bytes(dol[cave:cave + len(code)])
    current_hook = bytes(dol[hook:hook + 4])
    jump = struct.pack(">I", encode_branch(LAUNCHER, CAVE))
    if current_cave not in (b"\0" * len(code), code):
        raise SystemExit(f"cave {CAVE:#010x} is not free")
    if current_hook not in (ORIGINAL_FIRST, jump):
        raise SystemExit(f"unexpected launcher instruction {current_hook.hex()}")
    if off:
        dol[cave:cave + len(code)] = b"\0" * len(code)
        dol[hook:hook + 4] = ORIGINAL_FIRST
        print("Close Call test aid off")
    else:
        dol[cave:cave + len(code)] = code
        dol[hook:hook + 4] = jump
        print(f"Every board 4P minigame now launches table entry {NEW_INDEX} (Close Call)")
    DOL.write_bytes(dol)


if __name__ == "__main__":
    main()
