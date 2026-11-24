"""E. Gadd's Garage: space 27 (blue) becomes a Miracle space.

Space 27 (1, 811, -2399) is on the central turntable, directly below the hub, between 26 (a Star spot, left alone
because the Star-move code turns a spot blue when the Star leaves) and 25. The turntable already carries a Miracle
space (58), and the turntable code only moves spaces, it never rewrites their kind.

Space kind is the u16 at masu +0x30 (1 blue, 4 Miracle). Patches file 0 of root/data/w02.bin and w02n.bin (day and
night are identical), backups in decompiling/backups/*.bak_before_egadd_miracle. Idempotent. Not run in Dolphin.
"""
import shutil
import struct

from tools.lib import mpdata
from tools.lib.boards import load_spaces, replace_file0
from tools.lib.boards import kind_offset
from tools.lib.paths import BACKUPS, GAME_DATA

BOARDS = ("w02", "w02n")
CHANGES = ((27, 1, 4),)  # (space id, old kind, new kind): blue -> Miracle


def patch(board):
    path = GAME_DATA / f"{board}.bin"
    data, offsets = mpdata.read_archive(path)
    blob, start, end = load_spaces(data, offsets)
    changed = []
    for space_id, old_kind, new_kind in CHANGES:
        at = kind_offset(blob, space_id)
        current = struct.unpack_from(">H", blob, at)[0]
        if current == new_kind:
            continue
        if current != old_kind:
            raise RuntimeError(f"{board}: space {space_id} kind is {current}, expected {old_kind}")
        struct.pack_into(">H", blob, at, new_kind)
        changed.append(f"{space_id}: {old_kind} -> {new_kind}")
    if not changed:
        print(f"{board}: nothing to change")
        return
    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = BACKUPS / f"{board}.bin.bak_before_egadd_miracle"
    if not backup.exists():
        shutil.copy2(path, backup)
    packed, _ = replace_file0(data, offsets, start, end, blob)
    path.write_bytes(packed)
    print(f"{board}: space kinds " + ", ".join(changed))


def main():
    for board in BOARDS:
        patch(board)


if __name__ == "__main__":
    main()
