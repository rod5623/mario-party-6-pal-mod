# tools: how to build and patch

All commands are run from `src/` (the folder with `configure.py`).

**Prerequisites:**
- `tools/bin/` holds `dtk-windows-x86_64.exe` and `ninja.exe`, plus `VGAudioCli.exe` if you want
  the Close Call minigame.
- `build/GP6P01/` exists (run `configure.py` and ninja first).
- `../root/` holds your GCR extract of the game.

See the [top-level README](../../README.md). Writing your own patch? Read
[../docs/patching-guide.md](../docs/patching-guide.md) first.

## Quick start

```powershell
python .\tools\apply_all.py                 # apply every patch in the right order
python .\tools\apply_all.py --list          # show the order
```

Then copy the results into the game folder (see [Deploying](#deploying-to-the-game-folder)).

`apply_all.py` options:

| Option | What it does |
|---|---|
| `--list` | Print the steps in order and exit. |
| `--from NAME` | Start at step `NAME` (use this to resume after a failure). |
| `--only NAME ...` | Run just these steps, always in the table order, whatever order you type them in. |
| `--ninja` | First rebuild `build\GP6P01\main.dol` from the asm listings, then patch. The patches also edit those asm listings, so this is not a pristine DOL. |
| `--test-aids` | Also run `battle_always`, `duel_test_aid` and `closecall_always` (testing helpers, off by default). |

A step is the script `patches/apply_<NAME>_patch.py`. If a step fails, the run stops and prints the
`--from` command to resume.

## Choosing which patches to apply

You don't have to apply everything. Pick a bundle below, or build your own set from the
dependency table, and pass it to `--only`. Start from a fresh build (see
[Starting over](#if-something-goes-wrong)): `--only` doesn't undo patches already applied.

### Bundles

Every command below was tested from a fresh build. Several bundles can be combined: list all
their steps in one `--only`.

| Bundle | Command | Also brings in |
|---|---|---|
| Bowser and DK spaces | `--only dk_split dk_bonus bowser_bonus bowser_bonus_fix bowser_minigame` | — |
| Bonus Stars (random draw, wins-based Mini-game Star) | `--only random_bonus minigame_wins` | — |
| Sound (voice clips, win sound, quieter SFX and music) | `--only music_volume sfx` | — |
| Small tweaks | `--only final_five_odds star_trap_orb dunk_bros miracle_odds minigame_odds unlock_all music_volume cpu_landing` | — (each one also works alone) |
| Minigames (Battle and Duel ports, Close Call, time limits, exclusions) | `--only mgtable_move whatgoesup_battle cpu_handicap battle_ports battle_thumbs daft_rafts_duel lift_leapers_duel closecall 1v3_time_limit minigame_exclusion` | — |
| Faire Square | `--only mgtable_move star_shuffle_bet whomp_rich double_or_nothing battle_thumbs wheel_of_fortune luck_wheel_rewards faire_square_dk_bowser_space` | Battle roulette thumbnails |
| Castaway Bay | `--only star_trap_orb mgtable_move battle_thumbs wheel_of_fortune luck_wheel_rewards castaway_wheel boo_day_orbs castaway_broom castaway_spare_change castaway_troll` | Star Trap orb, Faire Square Wheel of Fortune and Luck Wheel, Boo by day (all boards) |
| E. Gadd's Garage | `--only star_trap_orb mgtable_move battle_thumbs wheel_of_fortune luck_wheel_rewards castaway_wheel castaway_broom castaway_spare_change egadd_wheel egadd_calamity egadd_shuffle egadd_morpher egadd_robots egadd_miracle_space` | Star Trap orb, Faire Square wheels, Castaway wheel, broom and spare change guy |
| Unlucky Star | the E. Gadd's Garage steps plus `random_bonus minigame_wins unlucky` | everything E. Gadd's Garage brings in |

The board bundles are long because of shared code. The Castaway Bay and E. Gadd's Garage
events reuse the Faire Square wheel's spin code. E. Gadd's code lives in DOL section 16, which
the Castaway spare change guy creates. The Unlucky Star's code lives in section 17, which the
Orb Morpher creates. `egadd_miracle_space` on its own needs nothing.

### Dependency table

- **Needs:** steps that must be in the same run. The script stops with an error if they're
  missing.
- **Needed in game:** steps the script doesn't check for, but without which part of the
  feature doesn't work.

Steps with nothing in either column can be applied on their own.

| Step | Needs | Needed in game | Notes |
|---|---|---|---|
| `dk_split` | — | — | DK space 50/50 Bonus/Mini-Game |
| `dk_bonus` | — | — | New DK Bonus faces. Independent of `dk_split`. |
| `bowser_bonus` | — | — | |
| `bowser_bonus_fix` | — | — | Replaces `bowser_bonus`'s outcomes. If you use both, it must run after it (the table order does this). |
| `random_bonus` | — | `minigame_wins` | Without it the Mini-game Star counts 0 wins for everyone. Copies its DOL, REL and messages into `root/` itself. |
| `minigame_wins` | — | `random_bonus` | Counts wins; only `random_bonus` uses the count. |
| `bowser_minigame` | — | — | Appends to the Bowser bank. Re-run it after re-running `bowser_bonus`/`bowser_bonus_fix`. |
| `final_five_odds`, `star_trap_orb`, `dunk_bros`, `miracle_odds`, `minigame_odds`, `unlock_all`, `music_volume`, `cpu_landing` | — | — | Independent tweaks |
| `sfx` | — | — | Rebuilds `sound/MP6_SND.msm` from the retail file: new voice clips in banks 000C/000E, other banks −2 dB. Takes about 2 minutes. See [../docs/audio.md](../docs/audio.md). |
| `mgtable_move` | — | — | Moves the minigame table so it can grow. Required by most later steps. |
| `star_shuffle_bet` | `mgtable_move` | — | |
| `whomp_rich` | `mgtable_move` | — | |
| `double_or_nothing` | — | `star_shuffle_bet` | Its question is a message that `star_shuffle_bet` adds. Without it the space shows the wrong text. |
| `whatgoesup_battle` | `mgtable_move` | — | Table entry 82 |
| `cpu_handicap` | `mgtable_move` | — | |
| `battle_ports` | `whatgoesup_battle` | — | Entries 83–85. Entries must be added in order. |
| `battle_thumbs` | `mgtable_move` | `battle_ports` | Thumbnails for the added Battle games |
| `daft_rafts_duel` | `battle_ports` | — | Entry 86 |
| `lift_leapers_duel` | `daft_rafts_duel` | — | Entry 87 |
| `closecall` | `lift_leapers_duel` | — | Entry 88. Needs `tools/bin/VGAudioCli.exe` for its music. |
| `1v3_time_limit` | — | — | |
| `minigame_exclusion` | `mgtable_move` | — | Excludes the games in `excluded_minigames.txt`. Run with the ports so they can be excluded too. |
| `wheel_of_fortune` | `mgtable_move`, `battle_thumbs` | — | Its icon goes after the thumbnails in `board*.bin` |
| `luck_wheel_rewards` | `wheel_of_fortune` | — | |
| `faire_square_dk_bowser_space` | — | — | Board file only |
| `castaway_wheel` | `luck_wheel_rewards`, `star_trap_orb` | — | Its model goes after the Star Trap orb's in `capsule.bin` |
| `boo_day_orbs` | `luck_wheel_rewards` | — | Uses the Luck Wheel's orb routine. Applies to every board with a Boo house. |
| `castaway_broom` | `castaway_wheel` | — | `boo_day_orbs` is optional |
| `castaway_spare_change` | `castaway_broom` | — | Adds DOL section 16 |
| `castaway_troll` | `castaway_spare_change` | — | |
| `egadd_wheel` | `castaway_spare_change` | — | Reuses the Castaway wheel's code. `castaway_troll` is optional. |
| `egadd_calamity` | `egadd_wheel` | — | |
| `egadd_shuffle` | `egadd_wheel` | — | |
| `egadd_morpher` | `egadd_wheel` | `egadd_calamity`, `egadd_shuffle` | Reuses message records those two make unreachable. Without them some vanilla messages show the Morpher's text. Adds DOL section 17. |
| `egadd_robots` | `egadd_morpher` | — | |
| `egadd_miracle_space` | — | — | Board file only |
| `unlucky` | `egadd_morpher` | `random_bonus` | `random_bonus` resets the counter and awards the Unlucky Star. Without it the counter does nothing. |

"Needs" is transitive. For example, `closecall` needs `lift_leapers_duel`, which needs
`daft_rafts_duel`, and so on back to `mgtable_move`. Add the whole chain.

## Order and why

`--only` and the full run both use the order of `STEPS` in `apply_all.py`:

| Group | Steps | Why here |
|---|---|---|
| A. Message-bank owners | `dk_split`, `dk_bonus`, `bowser_bonus`, `bowser_bonus_fix`, `random_bonus`, `minigame_wins` | Each writes only its own message bank, so they don't overwrite each other. `random_bonus` and `minigame_wins` run ninja, so they must come before any patch that edits only the binary DOL. |
| B. Chained message patches | `bowser_minigame`, `final_five_odds`, `star_trap_orb` | They build on the current message files. `bowser_minigame` appends to the Bowser bank, so it comes after `bowser_bonus` and `bowser_bonus_fix`. |
| C. Independent tweaks | `dunk_bros`, `miracle_odds`, `minigame_odds`, `unlock_all`, `music_volume`, `sfx`, `cpu_landing` | No ordering between them. `dunk_bros` edits the minigame table, so it comes before `mgtable_move`. `sfx` writes only `sound/MP6_SND.msm`. |
| D. Table move | `mgtable_move` | Relocates the minigame table. It edits only the binary DOL, so **nothing may rebuild the DOL with ninja after it**. |
| E. Needs the moved table | `star_shuffle_bet`, `whomp_rich`, `double_or_nothing`, `whatgoesup_battle`, `cpu_handicap`, `battle_ports`, `battle_thumbs`, `daft_rafts_duel`, `lift_leapers_duel`, `closecall`, `1v3_time_limit`, `minigame_exclusion`, `wheel_of_fortune`, `luck_wheel_rewards` | Their caves or table entries live in the relocated table's section. Inside the group, the order follows the dependency table above. |
| F. Board files | the rows below | Edit `root/data` directly as well as `build/`. Backups of board files go to `backups/`. |

Group F, step by step:

| Step | Board | What it touches |
|---|---|---|
| `faire_square_dk_bowser_space` | Faire Square | `root/data/w03*.bin` space kinds only |
| `castaway_wheel` | Castaway Bay | DOL caves after the Luck Wheel's; hooks `w05Dll.rel`; message bank 0x33 records 51–58; `capsule.bin` model; `board*.bin` icons; flag on space 20 in `root/data/w05*.bin` |
| `boo_day_orbs` | all Boo houses | DOL caves `0x80231100`–`0x80231860`, hook `0x801B1734`, bank 0x3B records 18–24. No board file. |
| `castaway_broom` | Castaway Bay | DOL caves `0x80231860`–`0x802326F0`; hooks `w05Dll.rel` .text 0x21BC and 0x1D18; space 26 and files 46–47 in `root/data/w05*.bin` |
| `castaway_spare_change` | Castaway Bay | Adds DOL section 16 (`0x802F7DA0`–`0x802F8DA0`) and raises the arena clamp; re-points `w05Dll.rel` .text 0x2300 (calls the wheel's cave first) and 0x1C2C; bank 0x33 records 60–68; new space 100 and card file 48 |
| `castaway_troll` | Castaway Bay | Section 16 after the spare change guy; chains the broom landing and spare change init caves; space 39, file 49; bank 0x33 records 69–72 |
| `egadd_wheel` | E. Gadd's Garage | Section 16 `0x802F87C0`–`0x802F8D70`; reuses the Castaway wheel's spin and random-orb caves; hooks `w02Dll.rel` .text 0x3A0C and 0x1B44; bank 0x30 records 27–33; flag on space 7 |
| `egadd_calamity` | E. Gadd's Garage | Calamity Launcher prices and CPU choice in `w02Dll.rel`; 12-byte cave at `0x802F8D70`; rewords bank 0x30 record 20 |
| `egadd_shuffle` | E. Gadd's Garage | Shuffle-o-tron works with 0 orbs and gives n+1 orbs below 3 (`w02Dll.rel` .text 0xB168, 0xB2AC); leaf at `0x802F8D80` |
| `egadd_morpher` | E. Gadd's Garage | Adds DOL section 17 (`0x802F8DA0`–`0x802F9DA0`) and raises the arena clamp; Orb Morpher payout (.text 0xB4F4); rewrites bank 0x30 records 8, 9, 10, 22 |
| `egadd_robots` | E. Gadd's Garage | Two robot cards (file 58) and the spare change event on new nodes 114/115; re-points the wheel's hooks to caves in section 17 (`0x802F8FA0`–`0x802F94A0`); bank 0x30 records 34–42 |
| `egadd_miracle_space` | E. Gadd's Garage | Space 27 becomes a Miracle space in `root/data/w02*.bin` |
| `unlucky` | all | Unlucky Star counter in section 17 (`0x802F9A00`); hooks the coin and Star setters |

Each script's docstring has the full details.

If you add a script, follow the checklist in
[../docs/patching-guide.md](../docs/patching-guide.md#10-adding-a-new-patch). Put it in the
right group of `STEPS` in `apply_all.py`, add a row to the dependency table above, and check it
doesn't overwrite another patch's output.

## Running one patch on its own

You can run a single script (`python -m tools.patches.apply_dk_bonus_patch`), and it is safe to
repeat. Know these first:

- **Run it after the steps it needs** (see the dependency table).
- **Don't re-run an early step alone after later ones have run.** Several patches rebuild a
  shared file and drop what later steps appended. For example, `wheel_of_fortune` resets
  `board*.bin` to its own icon and deletes the Castaway wheel's icons. Use
  `apply_all.py --from <step>` instead.
- **Message banks:** re-running `bowser_bonus` or `bowser_bonus_fix` resets the Bowser bank,
  which removes `bowser_minigame`'s text. Re-run `bowser_minigame` afterwards.
- **Never run ninja after `mgtable_move`.** Ninja rebuilds `main.dol` from the asm and drops
  every binary-only patch. If you must rebuild, start over.
- **`random_bonus` and `minigame_wins` run ninja.** Don't run them alone after group D or later.
  Run `apply_all.py` (or your `--only` set) from the start.
- **Asm-split RELs:** edits to `mdpresultdll` and `resultDll` listings aren't picked up by plain
  ninja. `lib/rebuild_mdpresult.py` assembles them, fetching binutils on first use.

## Deploying to the game folder

`apply_all.py` writes to `build\GP6P01\`. The board steps also write `root\data`, and
`random_bonus` copies its own files into `root`. Copy the rest yourself (paths from the
repository root):

| From | To |
|---|---|
| `src\build\GP6P01\main.dol` | `root\&&systemdata\Start.dol` |
| `src\build\GP6P01\files\dll\*.rel` | `root\dll\` |
| `src\build\GP6P01\files\data\*.bin` | `root\data\` |
| `src\build\GP6P01\files\mess\messdata*.bin` | `root\mess\` |
| `src\build\GP6P01\files\movie\*` | `root\movie\` (replaces existing files only, e.g. `dummy`) |
| `src\build\GP6P01\files\sound\MP6_Str.pdt` | `root\sound\` (music, with Close Call's track) |
| `src\build\GP6P01\files\sound\MP6_SND.msm` | `root\sound\` (sound effects, from `sfx`) |

Copy only files that exist: a subset run produces fewer files. Always copy the DOL and all
RELs together, because the patched overlays need the relocated table in the new DOL. Back up
`root` first (for example to a `root-backup` folder next to it).

Then build the ISO from `src/`: `python -m tools.scripts.build_iso` (writes
`srcuild\GP6P01-mod.iso`). None of the game behaviour is verified by the scripts; test in Dolphin.

## What is in this folder

`tools` is a Python package. Everything is run from `src/`, either through `apply_all.py` or as
a module: `python -m tools.<folder>.<module>`. Imports are absolute (`from tools.lib.dol import
dol_offset`), so a script can't be run by its file path.

| Folder | Contents |
|---|---|
| `apply_all.py` | Runs the patches in order (see above). |
| `patches/` | One `apply_<step>_patch.py` per step. `patches/test_aids/` holds `battle_always`, `duel_test_aid` and `closecall_always`, which only run with `--test-aids`. |
| `lib/` | Shared code the patches build on. See the table below. |
| `audio/` | Sound tools: `musyxextract.py` (by Nisto, included with credit), `patch_msm_bank.py` and `scale_msm_volume.py` (used by `sfx`), `msm_dump.py` (dump sound banks to DSP/WAV: `python -m tools.audio.msm_dump --bank 000C --wav`), `pdt.py` (append music to `MP6_Str.pdt`), `thp.py` (write THP movies). |
| `closecall/` | Builds the Close Call REL from C without ninja: `build_closecall_rel.py`, `closecall_assets.py`, and `p01_names.py`, which ports US symbol names onto P01 addresses (`build/GP6P01/include/p01_names.h`) and lists the P01 data directory numbers (`P01_DATA_*`). The US `DATA_*` values are wrong for Europe. |
| `scripts/` | Stand-alone helpers: `masu_dump.py` (dump a board's space table: `python -m tools.scripts.masu_dump w03`), `make_castaway_wheel_icons.py`, `build_iso.py` (rebuilds the ISO from `root/` with gclib, replacing GCR, and keeps new files: `python -m tools.scripts.build_iso`, base `src/orig/GP6P01.iso`, output `src/build/GP6P01-mod.iso`). |
| `assets/` | Art, models, music and the replacement sound clips (`assets/sfx/<bank>/*.dsp`) used by the patches. See `assets/NOTICE.md`. |
| `bin/` | Put `ninja.exe`, `dtk-windows-x86_64.exe` and `VGAudioCli.exe` here, plus `vgmstream/` for audio work. Not tracked. |
| `excluded_minigames.txt` | The list read by `minigame_exclusion`. |
| `project.py`, `download_tool.py`, `ninja_syntax.py`, `decompctx.py`, `transform_dep.py`, `upload_progress.py` | Decomp project build tooling from the upstream template. Used by `configure.py`, not by the patches. |

`lib/` modules:

| Module | What it has |
|---|---|
| `paths.py` | Every shared path: `ROOT` (= `src/`), `BUILD`, `DOL`, `ORIG`, the message, REL and data folders, `GAME_DATA` (`root/data`), `BACKUPS`, `ASSETS`, `BIN`. |
| `dol.py` | `dol_offset`, `encode_branch`, `replace_bytes`, `write_cave`, and the asm-listing edits (`patch_asm_instruction`, `patch_asm_word`, `patch_word_table`). |
| `ppc.py` | The `Asm` assembler, the `i_*` instruction encoders and opcodes, `prologue`/`epilogue`. |
| `rel.py` | REL relocations: `walk_relocs`, `import_blocks`, `add_calls`, `retarget_call`, `check_words`, `text_base`. |
| `messages.py` | Message files: `encode`, `record`, `write_bank` (own a bank), `edit_bank` / `append_records` (append to a shared bank). |
| `game.py` | Game function and global addresses shared by several patches (`FN_*`, `GW_PLAYER`, `GW_SYSTEM`). |
| `minigames.py` | MgDataTbl layout (`OLD_BASE`, `NEW_BASE`, `ENTRY_SIZE`, `SECTION_SLOT`) and `emit_type_check`. |
| `boards.py` | Board space tables: `lz_decode`, `load_spaces`, `replace_file0`, `flag_offset`, `kind_offset`. |
| `mpdata.py` | `data/*.bin` archives and sprites (ANM/CMPR). |
| `battle_port.py` | The recipe for porting 4P minigames into the Battle pool. |
| `battle_thumbnails.py`, `hsf_build.py` | Battle roulette thumbnails; small HSF models. |
| `rebuild_mdpresult.py` | Reassembles and relinks an asm-split REL (`mdpresultdll`, `resultDll`); fetches binutils on first use. |

Patches still import from each other where one builds on another's work (cave addresses,
appended message records, section layouts). For example, `castaway_troll` imports
`apply_castaway_spare_change_patch` for its section 16 layout. Those imports are the real
dependencies listed in the dependency table.

## Tests

```powershell
python -m pytest              # from src/: unit and consistency tests, a few seconds
ruff check ..                 # lint; ruff.toml is at the repository root
```

Install the tools once with `pip install -r requirements-dev.txt` (repository root). GitHub
Actions runs both on every push (`.github/workflows/tests.yml`).

The tests need no game files. They live in `src/tests/`:

- **Unit tests** for `lib/` (`ppc`, `dol`, `rel`, `messages`, `mpdata`, `boards`, `minigames`)
  and `audio/` (`musyxextract`, `pdt`, `scale_msm_volume`). The inputs are tiny synthetic DOLs,
  RELs, message files, archives and board tables made by `tests/builders.py`.
- **Consistency checks** (`test_consistency.py`): every step in `STEPS` has a script and every
  script is a step; every module imports without reading files; patch scripts have a docstring
  and `main()`; the dependency table above lists each step once, with its Needs earlier in
  `STEPS`; each bundle includes all its Needs; the layout rules in `AGENTS.md`; referenced assets
  exist.

Known problems are marked `xfail` with the reason, so they show as `x` until fixed.

There are no tests that run the patches against real game files yet. For those, still follow
"Verifying a change" in `AGENTS.md`.

## If something goes wrong

- **A step fails:** read the error. If it says `Run apply_X_patch.py first`, add that step (see
  the dependency table). Otherwise fix the problem and run `python .\tools\apply_all.py --from <step>`.
- **A message you added is missing in game:** a later or repeated script may have reset its
  bank. Re-run the owning script, then the ones that chain after it.
- **Patches seem lost after a rebuild:** ninja rebuilt `main.dol` from the asm. Start over.
- **Starting over (fresh build):** ninja can't give back an unpatched DOL, because the patches
  edit the asm listings in `build\GP6P01\asm` too. Delete `src\build\GP6P01`, then run
  `configure.py` and ninja again. Restore `root` from your backup.
