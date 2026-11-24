"""Change Faire Square space kinds (see CHANGES): python -m tools.patches.apply_faire_square_dk_bowser_space_patch

Space kind is the u16 after the flags in each space record (masu +0x30, read by fn_80177100): 1 blue, 6 DK (day) /
Bowser (night). Patches file 0 of root/data/w03.bin and w03n.bin; file 0 is re-stored as zlib (decode type 7).
Idempotent.
"""
import struct

from tools.lib import mpdata
from tools.lib.boards import kind_offset
from tools.lib.boards import lz_decode
from tools.lib.paths import GAME_DATA

ROOT = GAME_DATA
# (space id, old kind, new kind): 9 blue -> DK/Bowser, 106 blue -> Miracle (3 before the start, 1 before duel space 5)
CHANGES = ((9, 1, 6), (106, 1, 4))


def patch(board):
    path = f"{ROOT}/{board}.bin"
    data, offsets = mpdata.read_archive(path)
    start, end = mpdata.file_bounds(data, offsets, 0)
    size, kind = struct.unpack_from(">II", data, start)
    blob = bytearray(lz_decode(data[start + 8:end], size) if kind == 1 else mpdata.read_file(data, offsets, 0))
    changed = []
    for space_id, old_kind, new_kind in CHANGES:
        at = kind_offset(blob, space_id)
        current = struct.unpack_from(">H", blob, at)[0]
        if current == new_kind:
            continue
        assert current == old_kind, f"{board}: space {space_id} kind is {current}, expected {old_kind}"
        struct.pack_into(">H", blob, at, new_kind)
        changed.append(f"{space_id}: {old_kind} -> {new_kind}")
    if not changed:
        print(f"{board}: nothing to change")
        return

    packed = mpdata.pack_file(bytes(blob))
    delta = len(packed) - (end - start)
    out = data[:start] + packed + data[end:]
    new_offsets = [o + delta if o > start else o for o in offsets]
    out = struct.pack(">I", len(offsets)) + struct.pack(f">{len(offsets)}I", *new_offsets) + out[4 + 4 * len(offsets):]
    open(path, "wb").write(out)
    print(f"{board}: space kinds " + ", ".join(changed))


def main():
    for name in ("w03", "w03n"):
        patch(name)


if __name__ == "__main__":
    main()
