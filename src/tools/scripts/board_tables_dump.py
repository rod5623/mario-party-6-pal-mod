"""Print every board-set table and code site from tools.lib.board_tables: python -m tools.scripts.board_tables_dump

Reads build/GP6P01 (main.dol, files/dll/*.rel) where a file exists, else orig/GP6P01. Each table
is checked against its vanilla entry count and each site against its vanilla instruction; a
difference is marked CHANGED (a patch, or a wrong address). Long tables print their size and
the board-related rows only. Read-only. docs/board-tables.md explains the output.
"""
import sys

from tools.lib.board_tables import (
    BOARD_NO_READS, SITES, TABLES, clrlwi27, dol_string, read_site, read_table, read_word,
)
from tools.lib.paths import DOL, ORIG, REL_DIR, REL_ORIG

BOARD_OVERLAYS = range(0x7B, 0x83)  # w01dll..w11dll
SHORT = 12                          # tables up to this many rows print in full


def source(name):
    if name == "main.dol":
        candidates = (DOL, ORIG / "sys" / "main.dol")
    else:
        candidates = (REL_DIR / name, REL_ORIG / name)
    return next((path for path in candidates if path.exists()), None)


def show(value):
    if isinstance(value, float):
        return f"{value:g}"
    return hex(value) if abs(value) > 0xFF else str(value)


def board_rows(table, rows, dol):
    """(index, label) of the rows worth printing in a long table."""
    if table.name == "overlays":
        return [(i, dol_string(dol, r[0])) for i, r in enumerate(rows) if i in BOARD_OVERLAYS or i in (0x70, 0x79)]
    if table.name == "data_dirs":
        return [(i, dol_string(dol, r[0])) for i, r in enumerate(rows)
                if dol_string(dol, r[0]).startswith("data/w") and "mdl" not in dol_string(dol, r[0])]
    if table.name in ("sound_groups", "step_sounds"):
        return [(i, " ".join(show(v) for v in r)) for i, r in enumerate(rows) if r[0] in BOARD_OVERLAYS]
    return [(i, " ".join(show(v) for v in r[:4]) + (" ..." if len(r) > 4 else "")) for i, r in enumerate(rows)]


def main():
    blobs, missing = {}, set()
    for name in sorted({t.file for t in TABLES} | {s.file for s in SITES} | {r.file for r in BOARD_NO_READS}):
        path = source(name)
        if path is None:
            missing.add(name)
        else:
            blobs[name] = path.read_bytes()
            print(f"{name}: {path}")
    dol = blobs.get("main.dol")
    changed = 0

    for table in TABLES:
        where = f"{table.file} " + (f"section {table.section} +{table.where:#x}" if table.section
                                    else f"{table.where:#010x}")
        if table.file in missing:
            print(f"\n{table.name} ({where}): file missing")
            continue
        rows = read_table(blobs[table.file], table)
        status = "OK" if len(rows) == table.expected else f"CHANGED (vanilla {table.expected})"
        changed += status != "OK"
        print(f"\n{table.name}: {where}, {len(rows)} entries, {status}")
        print(f"  index: {table.index}\n  board 11: {table.board11}")
        listed = board_rows(table, rows, dol)
        if len(rows) > SHORT and table.name not in ("overlays", "data_dirs", "sound_groups", "step_sounds"):
            listed = listed[:SHORT] + [(len(rows) - 1, "...")]
        for index, label in listed:
            print(f"  [{index:3}] {label}")

    print("\nCode sites:")
    for site in SITES:
        if site.file in missing:
            print(f"  {site.name}: {site.file} missing")
            continue
        word = read_site(blobs[site.file], site)
        status = "OK" if word == site.word else f"CHANGED (vanilla {site.word:08X})"
        changed += status != "OK"
        print(f"  {site.name:22} {site.file} +{site.where:#x}: {word:08X} {status}")
        print(f"      {site.board11}")

    print("\nBoard-number reads (apply_clone_board_patch.py hooks them):")
    for read in BOARD_NO_READS:
        if read.file in missing:
            print(f"  {read.name}: {read.file} missing")
            continue
        word = read_word(blobs[read.file], read.file, read.where)
        if word == clrlwi27(read.rd, read.rs):
            status = "vanilla"
        elif word >> 26 == 18 and word & 1:
            status = "hooked (bl)"
        else:
            status = f"CHANGED ({word:08X})"
            changed += 1
        print(f"  {read.name:16} {read.file} +{read.where:#x}: {status}")

    print(f"\n{changed} changed" if changed else "\nAll tables and sites match vanilla.")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
