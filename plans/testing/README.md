# Plan: unit tests and static checks for the patch tools

**Status (2026-11-24): levels 1 and 3 are done.** The tests are in `src/tests/` and run in CI
(`.github/workflows/tests.yml`); see "Tests" in `src/tools/README.md`. The three problems they
found are fixed: `add_calls` now checks that the module-0 block is last before writing
anything, 11 patch scripts have docstrings, and `faire_square_dk_bowser_space` has a `main()`.
Level 2 and the cave registry ([Later](#later)) are not started.

Written for the agent (or person) who implements this. It covers **level 1** (unit tests of
`tools/lib` and `tools/audio` with synthetic data) and **level 3** (static and consistency
checks), both run on GitHub Actions. Level 2 (full-chain tests against a real disc) and a
cave registry are **out of scope**; see [Later](#later).

Read first: `AGENTS.md`, `src/tools/README.md` (layout, dependency table), and
`src/docs/patching-guide.md` sections 1–3.

## Constraints

- **No game data.** Tests must not read `src/orig/`, `src/build/` or `root/`, and must not need
  `tools/bin/*.exe`. Every input is built in the test from a few bytes. CI runs on a clean
  Linux machine.
- Run from `src/`: `python -m pytest`. `tools` is a package (absolute imports
  `from tools.lib.dol import ...`), so the working directory must be `src/`.
- Python 3.11. Pillow is needed because `tools/lib/mpdata.py` imports `PIL` at module level.
- **Don't change patch behaviour.** If a test exposes a bug, write it down and mark the test
  `xfail` with the reason. Fix it only if the user agrees.
- The project has two copies: `mario party 6/mp6-release/` (the GitHub tree) and
  `mario party 6/decompiling/` (the working copy). Implement in `mp6-release`, then copy
  `src/tests/`, `src/pytest.ini`, `ruff.toml` and any doc edits into `decompiling/src` and
  `decompiling/`. Never run `git add`/`commit`/`push`; the user does that.

## Layout to create

```
mp6-release/
  .github/workflows/tests.yml      CI (see below)
  ruff.toml                         lint config
  requirements-dev.txt              pytest, ruff (pins: tested versions)
  src/
    pytest.ini                      testpaths = tests; markers
    tests/
      __init__.py
      builders.py                   synthetic DOL / REL / messdata / archive / board builders
      test_ppc.py
      test_dol.py
      test_rel.py
      test_messages.py
      test_mpdata.py
      test_boards.py
      test_minigames.py
      test_audio.py                 musyxextract round trip, pdt header/parse
      test_consistency.py           level 3 checks that need Python (not ruff)
```

`src/pytest.ini`:
```ini
[pytest]
testpaths = tests
addopts = -q
markers =
    game: needs the user's disc files (level 2, not in CI)
```

## Builders (`tests/builders.py`)

Small functions that return `bytearray`s. Keep them minimal and commented with the format.

- `make_dol(sections)`: `sections` = list of `(kind, address, payload)`, with kind `"text"`
  (slots 0–6) or `"data"` (slots 7–17). The header is 0x100 bytes: file offsets at `0x00`
  (7 text) / `0x1C` (11 data), load addresses at `0x48` / `0x64`, sizes at `0x90` / `0xAC`.
  Payloads follow the header. Matches what `tools.lib.dol.dol_offset` reads.
- `make_messdata(banks)`: `banks` = list of lists of record bytes.
  - File: `u32 bank_count`, `u32 offset[bank]` (relative to byte 4), then the banks.
  - Bank: `u32 record_count`, `u32 offset[record]` (relative to bank start + 4), then the records.
  - Same layout as `messages.edit_bank` writes. Also write `read_bank(data, bank) -> list[bytes]`.
- `make_rel(text, relocs=())`: a minimal REL that `tools.lib.rel` can walk.
  - Header fields used: section table offset at `0x10`, `relOffset`/`impOffset`/`impSize` at `0x24`.
  - Section 1 is `.text`, with its file offset in the section table and bit 0 clear.
  - One import block for module 0 whose relocation list **is the last thing in the file**,
    because `add_calls` requires that: it starts with `R_DOLPHIN_SECTION` (202) for section 1
    and ends with `R_DOLPHIN_END` (203).
  - Read `text_base`, `walk_relocs`, `import_blocks` and `add_calls` before writing it.
- `make_archive(payloads)`: use `tools.lib.mpdata.pack_file` per payload and lay out `u32
  count, u32 offsets[count], files`. Also exercise the real `append_files`.
- `make_board_file0(spaces)`: a space table blob.
  - Layout: `u32 count`, then per space a 46-byte record followed by `2 * links` bytes of `u16`
    links.
  - Flags (`u32`) at +38, kind (`u16`) at +42, link count (`u16`) at +44.
  - That's what `flag_offset` and `kind_offset` walk.

## Level 1: unit tests

Prefer a few strong tests per function over many trivial ones. Each bullet is one test, or a
`pytest.mark.parametrize` table.

**`test_ppc.py` (`tools.lib.ppc`).** Anchor encoders to real instruction words from the game.
These were checked against the scripts on 2026-11-24:

| Call | Expected | Source of truth |
|---|---|---|
| `i_li(3, 2)` | `0x38600002` | `li r3,2`, `apply_boo_day_orbs_patch.HOOK_WORD` |
| `i_mem(LWZ, 0, 31, 0x374)` | `0x801F0374` | `lwz r0,0x374(r31)`, `apply_whatgoesup_battle_patch.SITE_A_OLD` |
| `i_mem(STWU, 1, 1, -0x30)` | `0x9421FFD0` | `stwu r1,-0x30(r1)`, `apply_cpu_landing_patch.HOOK_ORIGINAL` |
| `MFLR(0)`, `BLR` | `0x7C0802A6`, `0x4E800020` | standard |
| `i_mr(3, 26)` | `0x63430000` | **`ori` form.** The game's `mr` is the `or` form `0x7F43D378`; both do the same thing. Assert the `ori` form, with a comment. |

Then:
- `ha`/`lo` reconstruct any address: `(ha(a) << 16) + sign_extend16(lo(a)) == a`, including
  `lo >= 0x8000` cases such as `0x80008000`.
- `i_slwi(ra, rs, n) == i_rlwinm(ra, rs, n, 0, 31 - n)` for several `n`. Two definitions were
  merged on this equivalence, so lock it in.
- `i_extsh`, `i_extsb`, `i_add`, `i_subf`, `i_cmpwi`, `i_cmplwi`, `i_addis`, `i_mulli`: field
  placement. Decode the bit fields back (opcode `>> 26`, rD `>> 21 & 31`, …) instead of
  repeating the encoder.
- `Asm`:
  - forward and backward labels
  - every conditional in `branch()` (`beq bne blt bge ble bgt`) gets the right BO/BI and
    displacement
  - `.call(target)` gives the same word as `encode_branch(pc, target, True)`
  - `assemble()` length is `4 × words`
- `prologue`/`epilogue` with `saved=(30, 31)` and frame `0x20`:
  - the stack offsets match their docstring
  - the epilogue ends with `blr`
  - `epilogue` restores in the order `prologue` saved

**`test_dol.py` (`tools.lib.dol`).**
- `encode_branch(0x801BC87C, 0x8017E03C, link=True) == 0x4BFC17C1` and
  `encode_branch(0x801BC898, 0x801E705C, True) == 0x4802A7C5`. These are the real words in
  `apply_dk_bonus_patch.HOOKS`.
- `encode_branch` raises `ValueError` past ±32 MB and for unaligned targets. Test the exact
  boundary: `+0x1FFFFFC` passes, `+0x2000000` fails, and `-0x2000000` passes.
- `dol_offset` maps addresses in text and data sections, and raises for addresses outside all
  sections, including one past the end of a section.
- `replace_bytes`: original → patched; patched → unchanged (re-run); anything else → `RuntimeError`.
- `write_cave`: writes into zeros; accepts identical existing code; raises if different bytes
  are there.
- `patch_asm_instruction` / `patch_asm_word` / `patch_word_table` on small listing strings in
  dtk's format (`/* 80003100 00000000  38 60 00 00 */\tli r3, 0x0`). Cover the
  original → patched → re-run path and the error path. Copy real line shapes from a dtk listing;
  `patch_asm_word`'s regex is strict.

**`test_rel.py` (`tools.lib.rel`).**
- `walk_relocs` on a builder REL yields the expected `(section, offset, kind, target)` tuples.
- `add_calls(rel, [(0x10, 0x80004000)])`:
  - writes `48000001` at `.text+0x10`
  - appends one `R_PPC_REL24` to module 0, before `R_DOLPHIN_END`
  - returns 1
  - a second call returns 0 and leaves the bytes unchanged
  - two sites in one call are written in ascending order with correct deltas
- `add_calls` raises if the module-0 block isn't at the end of the file.
- `retarget_call`: changes the target; returns `False` if the target is already new; raises on
  a wrong old target and on a missing site.
- `check_words` accepts the original or `48000001` and raises otherwise.

**`test_messages.py` (`tools.lib.messages`).**
- `encode`:
  - `"Hi!?" → b"Hi\xc2\xc3"`
  - space → `0x10`, `,` → `0x82`, newline → `0x0A`
  - `"<N>"` → `1F 01`
- `record(header, body, end)` is padded to 4 bytes.
- `splice_bank`/`write_bank`:
  - replacing bank 1 of 3 shifts the bank offsets after it by the size difference
  - the other banks are byte-identical
  - `write_bank` uses the current output if it exists, else the source (use `tmp_path`)
- `edit_bank` (the core of every chained message patch):
  1. append to a vanilla bank → records = vanilla + append
  2. re-run on its own output → identical bytes
  3. a later patch's tail after ours is accepted only via `known_tails`, otherwise
     `RuntimeError`
  4. an older version of our tail in `known_tails` → rebuilt with the current one
  5. `replacements` change records in place
  6. banks after the edited one keep their content, and their offsets shift correctly
- `append_records`: append, then re-run is a no-op; a different extra tail → `RuntimeError`.

**`test_mpdata.py` / `test_boards.py`.**
- `pack_file` → `read_file` round trip (zlib type 7); `append_files` keeps the old files and
  offsets correct; `file_bounds`.
- `encode_cmpr`/`decode_cmpr`:
  - an 8×8 solid-colour image round-trips exactly
  - a gradient round-trips within a tolerance (CMPR is lossy)
  - build the images with Pillow in the test
- `flag_offset`/`kind_offset` on a builder board: right offsets for spaces 1 and 3 when space 2
  has links; `ValueError` for a missing id.
- `lz_decode`:
  - read the implementation (`decode type 1`, `HuDecodeLz`)
  - hand-craft a tiny stream with literals plus one back-reference, and check the output
  - if the format is unclear, test only an all-literals stream and note it
- `load_spaces` / `replace_file0` round trip on a builder archive whose file 0 is
  zlib-compressed. The offsets of later files shift by the size difference.

**`test_minigames.py`.**
- `emit_type_check` assembles without error.
- It contains `lis`/`addi` of `NEW_BASE` (check `ha`/`lo` fields) and ends in a `bne` to the
  given label.
- Constants: `NEW_END == NEW_BASE + NEW_SIZE` and `SECTION_SLOT == 15`.
- Pin the capacity limit described in `patching-guide.md` §8: 97 slots (indices 0–95 plus
  the terminator) must fit below the first section-15 cave at `NEW_BASE + 0x2F00`.
  `97 * ENTRY_SIZE <= 0x2F00` holds (`0x2EFC`); 98 slots would not.

**`test_audio.py`.**
- `tools.audio.musyxextract`:
  1. build a tiny `.sdir`/`.samp` pair for two samples with `write_sdir` and the header helpers
  2. `extract_samples` into `tmp_path`
  3. `pack_samples` the DSPs back
  4. the packed `.sdir` is identical, and `.samp` matches up to each sample's encoded size,
     because padding is zero-filled on pack
  - also check that pack order is sorted by file name
  - `samples_to_bytes`/`samples_to_nibbles` on known values (14 samples = 8 bytes per frame)
- `tools.audio.pdt`: `parse_dsp` and `track_from_dsp` on a synthetic mono DSP header.
- `tools.audio.scale_msm_volume`:
  - decode, then `encode_frames` at gain 1.0 with the original headers and coefficients, then
    decode again, on a small synthetic frame set. ADPCM re-encoding isn't guaranteed to be
    bit-exact, so find out whether the samples come back equal or only within ±1, then pin
    whichever holds.
  - At gain 0.5 the peaks halve within a tolerance.
  - `clamp16` boundaries.

## Level 3: static and consistency checks

**ruff (`ruff.toml` at the repo root):**
```toml
target-version = "py311"
line-length = 120
extend-exclude = ["src/build", "src/orig", "src/tools/bin"]
[lint]
select = ["F", "E9"]          # pyflakes errors and syntax errors only; no style churn
ignore = ["F841"]             # unused locals exist in older scripts; revisit later
[lint.per-file-ignores]
"src/tools/project.py" = ["F"]           # upstream files: leave untouched
"src/tools/download_tool.py" = ["F"]
"src/tools/decompctx.py" = ["F"]
"src/tools/transform_dep.py" = ["F"]
"src/tools/upload_progress.py" = ["F"]
"src/tools/ninja_syntax.py" = ["F"]
```
Run `ruff check .` from the repo root before writing tests. Fix only real problems (unused
imports are safe to remove). If anything else turns up, list it for the user.

**`test_consistency.py`** (pure Python, no game data):
1. **Steps ↔ files.** Every name in `apply_all.STEPS` has `tools/patches/apply_<name>_patch.py`.
   Every name in `TEST_AIDS` has one in `patches/test_aids/`. Every `apply_*_patch.py` file is in
   `STEPS` or `TEST_AIDS`. No duplicates.
2. **`--list` runs.** `subprocess.run([sys.executable, "tools/apply_all.py", "--list"], cwd=src)`
   prints `STEPS` in order.
3. **Every module imports.** Import every module under `tools/lib`, `tools/patches`,
   `tools/audio`, `tools/closecall` and `tools/scripts` with `importlib` (parametrize by
   module). Importing must not touch the filesystem. If a module reads files at import time, mark
   that case `xfail` and report it.
4. **Patch shape.** Each patch module:
   - has a module docstring
   - has `if __name__ == "__main__":`
   - defines `main`
5. **Dependency table ↔ STEPS.** Parse the "Dependency table" in `src/tools/README.md`:
   - every step appears in exactly one row (rows can list several steps, e.g. the "Independent
     tweaks" row)
   - every name in a "Needs" cell is a step
   - every "Needs" step comes **before** the dependent step in `STEPS`
6. **Bundles ↔ STEPS.** Parse each `--only ...` command in the "Bundles" table. Every name is a
   step, and the bundle is closed under "Needs": every step's Needs is also in the bundle. This
   is the check that keeps the README's tested bundles honest. The "Unlucky Star" row is prose
   ("the E. Gadd's Garage steps plus …"), so expand it explicitly in the test.
7. **Layout rules from AGENTS.md:**
   - No `Path(__file__)` outside `tools/lib/paths.py` and the upstream build files.
   - No `"../"` path strings in `tools/patches`, `tools/lib`, `tools/audio`, `tools/closecall`,
     `tools/scripts`.
   - **No lib name imported from a patch:** for each `from tools.patches.X import name`, `name`
     must not be defined in any `tools/lib` module. Shared helpers must come from `tools.lib`.
     Build the set of lib-defined names with `ast`.
8. **Assets referenced exist.** Every `ASSETS / "..."` string literal in the tools resolves to a
   file in `tools/assets/`. Use `ast` to find `BinOp` nodes with `Name(ASSETS)` on the left.

## CI (`.github/workflows/tests.yml` at the repo root)

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: ruff check .
      - run: python -m pytest -m "not game"
        working-directory: src
```

The patch tools use `pathlib` throughout, so the unit tests should pass on Linux. If anything
depends on Windows path separators, fix the test, not the tool. Run the suite locally on
Windows too.

## Docs to update when done

- `src/tools/README.md`: a short "Tests" section with how to run them (`python -m pytest` from
  `src/`), what they cover, and that game-file tests don't exist yet.
- `AGENTS.md`: add `python -m pytest` and `ruff check .` to Commands and to "Verifying a change".
- `src/docs/patching-guide.md` §10: add "add a unit test for any new `lib` helper; run
  `ruff check .` and `python -m pytest`".
- Top-level `README.md`: a CI badge is optional; ask the user.

## Definition of done

- `ruff check .` is clean (or every remaining finding is listed and agreed).
- `python -m pytest` passes locally on Windows in a few seconds, with no game files present.
  Test this by renaming `src/orig` temporarily, or by running from a fresh checkout copy.
- Coverage of `tools/lib` (`pytest --cov=tools.lib`, if `pytest-cov` is added) is reported to
  the user. Aim for every public function in `dol`, `ppc`, `rel` and `messages`.
- Every `xfail` lists the bug it documents, and the user is told about each.
- Files are copied into the `decompiling` working copy, and nothing is committed.

## Later

- **Level 2, game tests (`-m game`), local only.** Port the scratch harness used on 2026-11-24:
  - restore a pristine `build/GP6P01` snapshot
  - run `apply_all.py` (full and per bundle)
  - hash every output and compare with committed golden SHA-1s
  - run twice to check idempotency (expect `w03Dll.rel` to fail until its growth bug is fixed)

  Caveat: replacing `tools/` changes `download_tool.py`'s timestamp, and ninja then relinks
  `mdpresultdll`. Compare only runs made under the same conditions.
- **Cave registry.** Each patch declares its DOL/REL code ranges in a constant (e.g.
  `CAVES_USED = [(start, end), ...]`). A test asserts no overlaps and that every write
  stays inside the declared ranges. This would catch the "caves packed back to back" bug class.
