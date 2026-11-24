"""Build a GP6P01 ISO from root/ with gclib. Replaces GameCube Rebuilder (GCR) for the rebuild.

    python -m tools.scripts.build_iso [--add-test-file] [--base src/orig/GP6P01.iso] [--out src/build/GP6P01-mod.iso]

GCR rebuilds the disc from the original Game.toc, so it drops any file the original disc doesn't
have (this is why the patching guide forbids new files). gclib (LagoLunatic's library behind
GCFT, pinned in requirements.txt) writes a new FST instead: files can be added, and replaced
files can be any size.

gclib can't build a disc from nothing, so the base is the user's clean ISO. Every file in the
folder (GCR layout: &&systemdata/Start.dol plus the game folders) is compared with the base:
  - same bytes: left alone, read from the base ISO when the new disc is written;
  - different bytes: replaced;
  - not on the base disc: added as a new file.
Only the changed and added files are held in memory. GCR's other &&systemdata files (ISO.hdr,
AppLoader.ldr, Game.toc) and root/README.md are skipped: the system data comes from the base.

--add-test-file adds files/data/mp6mod_test.bin, a file the original disc doesn't have. It goes
in data/ on purpose: every FST entry after it gets a new number, which checks that the game
looks its data folders up by name (DVDConvertPathToEntrynum in data.c) and not by number.

After writing, the new ISO is opened again and every replaced or added file is compared with
its source. Status: confirmed in game (2026-11-24): with the test file added in data/, the
ISO boots in Dolphin and minigames play.
"""
import argparse
import os
import sys
from io import BytesIO
from pathlib import Path

from tools.lib.paths import BASE_ISO, GAME_ROOT, MOD_ISO

GCR_SYSTEM_DIR = "&&systemdata"
GCR_DOL = "Start.dol"
SKIPPED_TOP_LEVEL = {"README.md", ".gitkeep"}   # repo files kept in root/, not game files

TEST_FILE = "files/data/mp6mod_test.bin"
TEST_FILE_DATA = b"MP6 PAL mod: gclib new-file test\n".ljust(0x40, b"\0")

DISC_MAX_SIZE = 1_459_978_240   # a full-size GameCube disc
CHUNK = 16 * 1024 * 1024


def disc_path(relative):
    """Map a path in a GCR extract (posix, relative to it) to gclib's disc path, or None to skip."""
    parts = relative.split("/")
    if parts[0] == GCR_SYSTEM_DIR:
        return "sys/main.dol" if parts[1:] == [GCR_DOL] else None
    if len(parts) == 1 and parts[0] in SKIPPED_TOP_LEVEL:
        return None
    return "files/" + relative


def folder_files(folder):
    """Yield (disc path, file on disk) for every game file in a GCR extract, sorted."""
    folder = Path(folder)
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        target = disc_path(path.relative_to(folder).as_posix())
        if target is not None:
            yield target, path


def same_as_disc(iso, entry, path):
    """True if the file on disk has the same bytes as the entry in the open base ISO."""
    if path.stat().st_size != entry.file_size:
        return False
    iso.seek(entry.file_data_offset)
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                return True
            if iso.read(len(chunk)) != chunk:
                return False


def stage_changes(gcm, files, add_test_file=False):
    """Load changed and new files into gcm. Returns (replaced, added, kept_from_base) disc paths."""
    replaced, added, seen = [], [], set()
    with open(gcm.iso_path, "rb") as iso:
        for target, path in files:
            entry = gcm.files_by_path_lowercase.get(target.lower())
            if entry is not None:
                seen.add(entry.file_path)
                if not same_as_disc(iso, entry, path):
                    gcm.changed_files[entry.file_path] = BytesIO(path.read_bytes())
                    replaced.append(entry.file_path)
            else:
                gcm.add_new_file(target, BytesIO(path.read_bytes()))
                added.append(target)
                seen.add(target)
    if add_test_file and TEST_FILE.lower() not in gcm.files_by_path_lowercase:
        gcm.add_new_file(TEST_FILE, BytesIO(TEST_FILE_DATA))
        added.append(TEST_FILE)
        seen.add(TEST_FILE)
    kept = sorted(p for p in gcm.files_by_path if p not in seen and not p.startswith("sys/"))
    return replaced, added, kept


def write_iso(gcm, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    total = len(gcm.files_by_path)
    for name, done in gcm.export_disc_to_iso_with_changed_files(str(out)):
        if done % 200 == 0 or done == total:
            print(f"  writing {done}/{total} {name}")


def verify(out, gcm, targets):
    """Open the new ISO and compare each staged file of gcm with what landed on it. Raises on a mismatch.

    gclib sizes sys/main.dol by its sections when it reads a disc, so that entry can be shorter
    than the file written; for it the staged data only has to start with what is read back.
    """
    from gclib.gcm import GCM

    check = GCM(str(out))
    check.read_entire_disc()
    bad = []
    for target in targets:
        if target.lower() not in check.files_by_path_lowercase:
            bad.append(f"{target}: missing")
            continue
        on_disc = check.read_file_raw_data(target)
        with gcm.changed_files[target].getbuffer() as staged:
            expected = staged[:len(on_disc)] if target.startswith("sys/") else staged
            if on_disc != expected:
                bad.append(f"{target}: bytes differ")
    if bad:
        raise SystemExit("Verification failed:\n  " + "\n  ".join(bad))
    return check


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", type=Path, default=BASE_ISO,
                        help="your clean GP6P01 ISO (default: src/orig/GP6P01.iso)")
    parser.add_argument("--out", type=Path, default=MOD_ISO,
                        help="the ISO to write (default: src/build/GP6P01-mod.iso)")
    parser.add_argument("--folder", type=Path, default=GAME_ROOT,
                        help="GCR extract to build from (default: root/)")
    parser.add_argument("--add-test-file", action="store_true", help=f"also add {TEST_FILE}")
    args = parser.parse_args(argv)

    try:
        from gclib.gcm import GCM
    except ImportError:
        raise SystemExit("gclib is missing: pip install -r requirements.txt (repository root)")

    if not (args.folder / GCR_SYSTEM_DIR / GCR_DOL).is_file():
        raise SystemExit(f"{args.folder} doesn't look like a GCR extract (no {GCR_SYSTEM_DIR}/{GCR_DOL})")
    if not args.base.is_file():
        raise SystemExit(f"No base ISO at {args.base}: put your clean GP6P01 disc image there or pass --base")
    if args.out.exists() and os.path.samefile(args.out, args.base):
        raise SystemExit("--out is the base ISO; write to a new file")

    gcm = GCM(str(args.base))
    gcm.read_entire_disc()
    game_id = gcm.read_file_raw_data("sys/boot.bin")[:6]
    if game_id != b"GP6P01":
        raise SystemExit(f"Base ISO is {game_id!r}, expected b'GP6P01'")

    files = list(folder_files(args.folder))
    replaced, added, kept = stage_changes(gcm, files, args.add_test_file)
    print(f"{len(files)} files in {args.folder}: {len(replaced)} changed, {len(added)} new")
    for target in added:
        print(f"  new: {target}")
    if kept:
        print(f"{len(kept)} disc files are not in the folder and are kept from the base ISO, e.g. {kept[0]}")

    write_iso(gcm, args.out)
    size = args.out.stat().st_size
    print(f"Wrote {args.out} ({size / 2**20:.1f} MiB)")
    if size > DISC_MAX_SIZE:
        print(f"Warning: larger than a GameCube disc ({DISC_MAX_SIZE / 2**20:.1f} MiB)", file=sys.stderr)

    verify(args.out, gcm, replaced + added)
    print(f"Verified {len(replaced) + len(added)} changed and new files in the new ISO.")


if __name__ == "__main__":
    main()
