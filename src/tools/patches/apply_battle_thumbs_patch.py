"""Battle roulette thumbnails for the added Battle games.

The Battle choice screen (fn_801F3C4C) matches each choice's name message
(MgDataTbl entry +8) against a 6-row table at 0x8021AA58 (stride 0xC: name
message, night thumbnail, day thumbnail). That row also supplies the game's
title text. A game with no row reads past the table and crashes
("Invalid read ... PC = 0x80009114" in the data loader).

This copies the table to the relocated DOL section (10 rows), adds rows for the
Battle copies of m604, m615, m614 and m603, retargets the four lis/addi
references and the row-count compare (6 -> 10). Thumbnails of existing Battle
games are reused as placeholders (there is no art for the new games).
Run after apply_mgtable_move_patch.py.
"""
import struct

from tools.lib.paths import DOL
from tools.lib.dol import dol_offset, replace_bytes
from tools.lib.minigames import NEW_BASE
from tools.lib import battle_thumbnails as bt
from tools.lib import mpdata
from tools.lib.ppc import ha
from tools.lib.paths import DATA_ORIG, DATA_OUT

OLD_TABLE = 0x8021AA58
ROW_SIZE = 0xC
OLD_ROWS = 6
NEW_TABLE = NEW_BASE + 0x3000
MG_NAME = 0x50000  # message dir 5 (MG_NAME) | index

# (title message index, game) in the order of battle_thumbnails.GAME_ORDER
NEW_ROWS = [
    (3, "m604"),   # What Goes Up
    (14, "m615"),  # Note to Self
    (13, "m614"),  # Cannonball Fun
    (2, "m603"),   # Freeze Frame
]
BOARD_DIR = 5  # data directory number of board.bin
ROWS = OLD_ROWS + len(NEW_ROWS)

# lis/addi pairs that load lbl_8021AA58, and the row-count compare
REFERENCES = [0x801F3CB8, 0x801F3D18, 0x801F3D4C, 0x801F3E58]
COMPARE = 0x801F3CF0


def write_archives():
    DATA_OUT.mkdir(parents=True, exist_ok=True)  # bt.build writes its preview image here
    payloads = bt.build(DATA_ORIG, DATA_ORIG / "instpic.bin", DATA_OUT)
    for name in bt.BOARD_FILES:
        data, offsets = mpdata.read_archive(DATA_ORIG / f"{name}.bin")
        if len(offsets) != bt.FIRST_NEW_FILE:
            raise RuntimeError(f"{name}.bin has {len(offsets)} files, expected {bt.FIRST_NEW_FILE}")
        patched, _ = mpdata.append_files(data, offsets, payloads)
        (DATA_OUT / f"{name}.bin").write_bytes(patched)
    print(f"Wrote {len(bt.BOARD_FILES)} board archives with {len(payloads)} new thumbnails to {DATA_OUT}")


def main():
    dol = bytearray(DOL.read_bytes())
    old = dol_offset(dol, OLD_TABLE)
    rows = [bytes(dol[old + ROW_SIZE * i:old + ROW_SIZE * (i + 1)]) for i in range(OLD_ROWS)]
    if struct.unpack(">I", rows[0][:4])[0] != 0x5002D:
        raise SystemExit("Unexpected Battle thumbnail table")
    assert [g for _, g in NEW_ROWS] == bt.GAME_ORDER
    for number, (title, _) in enumerate(NEW_ROWS):
        day = (BOARD_DIR << 16) | (bt.FIRST_NEW_FILE + 2 * number)
        night = day + 1
        rows.append(struct.pack(">3I", MG_NAME | title, day, night))
    table = b"".join(rows)

    new = dol_offset(dol, NEW_TABLE)
    dol[new:new + len(table)] = table

    for address in REFERENCES:
        position = dol_offset(dol, address)
        lis_old, lis_new = ha(OLD_TABLE), ha(NEW_TABLE)
        replace_bytes(dol, position + 2, struct.pack(">H", lis_old), struct.pack(">H", lis_new), f"lis at {address:08X}")
        replace_bytes(dol, position + 6, struct.pack(">H", OLD_TABLE & 0xFFFF), struct.pack(">H", NEW_TABLE & 0xFFFF), f"addi at {address + 4:08X}")
    replace_bytes(dol, dol_offset(dol, COMPARE), bytes.fromhex("2C1B0006"), bytes.fromhex("2C1B%04X" % ROWS), "row count")
    DOL.write_bytes(dol)
    write_archives()
    print(f"Battle thumbnail table moved to {NEW_TABLE:#010x} with {ROWS} rows")


if __name__ == "__main__":
    main()
