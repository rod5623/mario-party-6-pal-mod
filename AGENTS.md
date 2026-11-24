# AGENTS.md

Instructions for AI coding agents working in this repository.

## What this is

A gameplay mod for **Mario Party 6 PAL (GP6P01)**. Python patch scripts in `src/tools/` edit
the game's `main.dol`, REL overlays, message files and data archives. New minigame code is C
in `src/src/REL/`. No game files are in the repo.

## Read first

1. **[src/docs/patching-guide.md](src/docs/patching-guide.md):** code space map, shared
   helpers, REL hooks, message banks and file formats. Read it before writing or changing any
   patch.
2. **[src/tools/README.md](src/tools/README.md):** step order, the dependency table (what each
   step needs), tested `--only` bundles and the deploy table.
3. The docstring of every script that touches the same file, cave, REL site or message bank as
   your change.

Audio changes (sound effects, voice clips, music) and how to make new ones:
[src/docs/audio.md](src/docs/audio.md).

Design notes: `boards/<board>/*.md` (board space numbers, layouts) and `plans/*/` (bonus stars,
orbs, minigame pools).

## Hard rules

- **Addresses are PAL.** US (GP6E01) names and addresses from the upstream decomp don't apply.
  US `DATA_*` directory numbers are wrong; use `P01_DATA_*` (`src/tools/closecall/p01_names.py`).
- **Patches must be idempotent.** Accept the original or your own patched bytes, and raise on
  anything else. Reuse `replace_bytes`, `write_cave` (`tools.lib.dol`) and `check_words`
  (`tools.lib.rel`).
- **Read the current output, else the original.** Write only what your patch owns.
- **Grep `src/tools/` (recursively) for every address near a cave before using or growing it.**
  Caves are packed back to back, and a declared limit may run into a neighbour.
- **Layout:** patches go in `src/tools/patches/`, shared code in `src/tools/lib/`. Get paths from
  `tools.lib.paths`, never from `__file__` or the working directory. Run scripts from `src/` as
  modules (`python -m tools.patches.apply_x_patch`); imports are absolute (`from tools.lib.dol
  import dol_offset`). Import another patch only for what it made: caves, records, sections.
- **Never run ninja after `mgtable_move` in the chain.** It rebuilds `main.dol` from asm and
  drops the binary-only patches.
- **Never add new files to the disc.** The GCR rebuild drops them. Append to existing archives
  or reuse placeholders.
- **Don't re-run one early step alone.** Run `python tools/apply_all.py --from <step>` to the
  end. Shared files are rebuilt by later steps.
- **New steps go in `STEPS` in `src/tools/apply_all.py`,** with a comment saying why they go
  there. Also add a row to the dependency table in `src/tools/README.md`, and test the step
  with `--only <step + its Needs>` from a fresh build.
- **Create output folders before writing** (`mkdir(parents=True, exist_ok=True)`). In a subset
  run, `build/GP6P01/files/<dir>/` may not exist yet.
- Reuse the helpers listed in section 3 of the patching guide instead of writing new encoders
  or parsers.

## Commands (from `src/`, Windows)

```powershell
python .\configure.py --version GP6P01 --dtk .\tools\bin\dtk-windows-x86_64.exe
.\tools\bin\ninja.exe          # ends with "main.dol: FAILED" on the hash check: known, expected
python .\tools\apply_all.py    # --list, --from NAME, --only NAME ..., --test-aids
python -m tools.scripts.masu_dump w05   # dump a board's space table from root/data
python -m pytest               # unit and consistency tests; no game files needed
ruff check ..                  # lint (config in ruff.toml at the repository root)
```

Test and lint tools: `pip install -r requirements-dev.txt` (repository root).

`src/tools/bin/` must hold decomp-toolkit v1.8.4 and Ninja 1.13.2, plus `VGAudioCli.exe` for
`closecall`, and optionally `vgmstream/` for audio work. The full download list is in the
top-level README. Binutils are fetched into `src/build/binutils` on first use. `src/orig/GP6P01/` holds the
user's Dolphin extract, and `root/` holds their GCR extract.

## Verifying a change

- Run `python -m pytest` (from `src/`) and `ruff check .` (from the repository root). Both must
  pass; CI runs them on every push. A new `tools/lib` helper needs a unit test in `src/tests/`.
- Run your script twice. The second run must change nothing (compare hashes).
- Run `apply_all.py --from <your step>` to the end. Diff `src/build/GP6P01` against a snapshot
  from before your change: only files you own should differ. The known exception is
  `w03Dll.rel`, which grows on every full run.
- In-game testing needs the user: deploy to `root/`, rebuild with GCR, run in Dolphin. Don't
  claim something works in game unless the user has confirmed it. Update the script's status
  note to match.

## Don't

- Commit or track game files (`orig/`, `root/`, `build/`, `.dol`, `.rel`, ISO images).
- Edit `src/config/` symbols or splits unless the task is about the decomp itself.
- Touch `backups/` contents. They are the only copy of the original board files.
