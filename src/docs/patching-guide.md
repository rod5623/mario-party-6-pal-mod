# Patching guide (GP6P01)

How the patch scripts in `src/tools/` change Mario Party 6 (PAL), and how to add a new one
without breaking the others. It is written for an LLM agent extending the mod first and a
human second, so it favours exact addresses, file names and rules over explanation.

All addresses are **GP6P01 (PAL)**. US (GP6E01) addresses and symbol names from the upstream
decomp are different. Paths are relative to `src/` unless they start with `root/`, `backups/`
or `boards/` (repository root).

The address tables below were collected from the scripts' constants on 2026-11-24. The scripts
are the source of truth. **Before you use any address, grep `tools/` (`grep -rn 0x8000XXXX tools/`) for it and for its
neighbours.**

---

## 1. Rules that have broken things before

1. **Every script must be idempotent.** Before writing, check that the bytes are either the
   original or already your patched value, and fail loudly otherwise. `replace_bytes()`,
   `write_cave()` and `check_words()` all do this. Users re-run `apply_all.py` many times.
2. **Order and dependencies matter.** `tools/apply_all.py` has a `STEPS` list with comments
   explaining each placement. `tools/README.md` has the tested **dependency table** (which steps
   need which) and tested bundles for `--only`. New steps go where their dependencies are
   satisfied (see section 10).
3. **Nothing may run ninja after `mgtable_move`.** Ninja rebuilds `main.dol` from the asm
   listings. Patches up to `mgtable_move` also edit the listings, so their changes survive a
   rebuild. Later patches edit the binary DOL only and would be lost. (`random_bonus` and
   `minigame_wins` run ninja themselves, which is why they come first.)
4. **New disc files only survive `build_iso`.** `python -m tools.scripts.build_iso` (gclib)
   writes a new FST, so files added to `root/` reach the disc; confirmed in game with a test
   file in `data/` (boots, minigames play). GameCube Rebuilder (GCR) follows the original
   `Game.toc` and silently drops new files: a missing movie once caused an endless black screen
   when GCR was the rebuild tool. A new file is still only useful if the game can find it: the
   data directories (`DataDirStat`, resolved by name in `data.c`) are a fixed table in the DOL,
   and music is addressed by track number. So data for an existing directory still goes into
   existing archives, tracks are appended to `sound/MP6_Str.pdt`, and placeholders such as
   `movie/dummy` and `dll/jbtestdll.rel` stay the simplest route. A whole new file (a new board's
   REL and archive) also needs the DOL table that names it extended.
5. **Don't re-run one early step on its own.** Several patches rebuild a shared file from its
   current state and drop anything appended after their own part. Example: `wheel_of_fortune`
   truncates `data/board*.bin` back to its own icon, which deleted the Castaway wheel icons
   that `castaway_wheel` appends later and caused heap corruption in game. Use
   `apply_all.py --from <step>` to the end, or the full chain.
6. **Caves are packed back to back.** A "not empty" check on your own cave misses your
   neighbour's. Growing `random_bonus`'s cave by one word once overwrote the first word of
   `whomp_rich`'s cave. Before growing a cave, grep for every address up to the next cave.
   Prefer an edit that needs no cave. For example, widening `sth r5,0x28` to `stw` at
   `0x8014C00C` zeroes `+0x2A` for free.
7. **Text is English in all six languages.** Patches write the English text into all six
   `messdata*.bin` files, so play in English. Some older patches change only `messdata_eng.bin`.
8. **Known issue: `w03Dll.rel` grows on every full chain run.** `wheel_of_fortune` adds 24 bytes
   and `luck_wheel_rewards` adds 16 bytes of duplicate relocations, then `mgtable_move`
   re-retargets them. Each script is stable on its own. This is not fixed yet. After repeated
   test runs, restore `build/GP6P01/files/dll/w03Dll.rel` from a snapshot.
9. **PAL runs at 50 fps.** Frame counts and timers (`li r4, N` in 1/50 s ticks) are PAL values.

---

## 2. Pipeline and the files patches touch

```
orig/GP6P01/ (Dolphin extract, read-only)
   │ configure.py + ninja (dtk split, mwcc build)
   ▼
build/GP6P01/
   asm/*.s                listings: early patches edit these so ninja rebuilds keep them
   main.dol               the DOL every patch edits
   files/dll/*.rel        patched REL copies (created from orig/ on first edit)
   files/data/*.bin       patched data archives (capsule.bin, board*.bin, saf.bin, instpic.bin ...)
   files/mess/messdata*.bin   patched message files (6 languages)
   files/movie, files/sound   patched movies, music (MP6_Str.pdt) and sound effects (MP6_SND.msm); see audio.md
root/data/w0X*.bin       board files: the board patches edit root/ directly
backups/*.bak_before_<patch>   copies of root/ board files taken before the first edit
```

- **Input rule:** read the current output if it exists, else the original from `orig/`. That
  is how patches chain on the same file, e.g.
  `data = (built if built.exists() else source).read_bytes()`.
- **Deploy:** outputs are copied into `root/` (see the top-level README), and the ISO is rebuilt
  with `python -m tools.scripts.build_iso`. `main.dol` goes to `root/&&systemdata/Start.dol`.
- **Asm listing names:** `ASM_INIT` = `asm/auto_00_80003100_init.s`,
  `ASM_TEXT` = `asm/auto_03_800EF6C8_text.s` (there is also `auto_03_80005920_text.s`),
  `ASM_DATA` = `asm/auto_07_80259D80_data.s`, `ASM_SDATA` = `asm/auto_09_802DCE00_sdata.s`.
  Each instruction line contains `/* ADDRESS ` and its bytes, which the asm patch helpers match on.

---

## 3. Shared helpers (reuse these; don't write new ones)

`tools` is a Python package (layout in `tools/README.md`). Patches live in `tools/patches/`,
shared code in `tools/lib/`, and everything runs from `src/` as a module, e.g.
`python -m tools.patches.apply_dk_bonus_patch`. Imports are absolute. Import generic helpers
from `tools.lib`. Import another patch (`from tools.patches import apply_castaway_wheel_patch as
cw`) only for what that patch *made*: its cave addresses, appended records, section layout.

| Helper | Module | Purpose |
|---|---|---|
| `ROOT` (= `src/`), `BUILD`, `ORIG`, `DOL`, `ASM_*`, `MESS_SOURCE_DIR`/`MESS_OUTPUT_DIR`, `MESS_NAMES`, `REL_DIR`/`REL_ORIG`, `DATA_ORIG`/`DATA_OUT`, `GAME_DATA` (`root/data`), `BACKUPS`, `ASSETS`, `BIN` | `tools.lib.paths` | Every shared path. Never compute paths from `__file__` or the working directory. |
| `dol_offset(dol, address)` | `tools.lib.dol` | Virtual address to DOL file offset, using the header's 7 text + 11 data sections. Raises if the address is not in a section. |
| `encode_branch(source, target, link=False)` | `tools.lib.dol` | `b` / `bl` word, range-checked (±32 MB). |
| `replace_bytes(data, offset, original, patched, desc)` | `tools.lib.dol` | Idempotent byte swap: accepts original or patched, otherwise raises. |
| `write_cave(dol, address, code)` | `tools.lib.dol` | Write a cave only if the area is zero or already this code. |
| `patch_dol_instruction`, `patch_asm_instruction`, `patch_asm_word`, `patch_word_table` | `tools.lib.dol` | The same swap for the DOL and for asm listing lines and tables. |
| `Asm(base)` | `tools.lib.ppc` | Tiny assembler: `.word()`, `.label()`, `.branch("beq"/"bne"/"blt"/"bge"/"ble"/"bgt"/"b", label)`, `.call(addr)` (bl), `.assemble()` → bytes. |
| `i_addi`, `i_addis`, `i_lis`, `i_li`, `i_ori`, `i_mem(op, rt, ra, imm)`, `i_mr`, `i_cmpwi`, `i_cmplwi`, `i_cmpw`, `i_add`, `i_subf`, `i_mullw`, `i_divw`, `i_slwi`, `i_srawi`, `i_rlwinm`, `i_extsh`, `i_extsb`, `i_mulli`, `i_lwzx`, `i_lbzx`, `i_clrlwi24`, `i_fadds`, `ha`, `lo`; opcodes `LWZ STW LBZ LHZ LHA STH STB STWU LFS`; `MFLR MTLR MTCTR BCTR BLR`; `b_to` | `tools.lib.ppc` | PowerPC instruction encoders. |
| `prologue(a, frame, saved)` / `epilogue(a, frame, saved)` | `tools.lib.ppc` | Stack frame and callee-saved registers for a cave function. |
| `text_base`, `walk_relocs`, `import_blocks`, `add_calls`, `retarget_call`, `check_words`, `R_PPC_REL24` | `tools.lib.rel` | REL relocation tools (section 5). |
| `OLD_BASE`, `NEW_BASE`, `NEW_END`, `ENTRY_SIZE`, `SECTION_SLOT`, `MG_TYPE_BATTLE`, `emit_type_check` | `tools.lib.minigames` | MgDataTbl layout. `emit_type_check` branches unless `MgDataTbl[GwSystem.mgNo].type` equals a value. |
| `add_table_entry(dol, src_index, new_index, mg_type)` and the Battle-port recipe | `tools.lib.battle_port` | Copy a minigame table entry with a new type; hook a ported REL. |
| `write_bank`, `splice_bank` | `tools.lib.messages` | Replace one message bank (section 6). |
| `edit_bank(source, replacements, label, bank, bank_records, append, known_tails)` | `tools.lib.messages` | Replace and append records in one bank, accepting older versions' tails. |
| `append_records(source, {bank: (orig_count, records)}, label)` | `tools.lib.messages` | Simpler append. |
| `encode(text)`, `record(header, body, end)`, `INDENT` | `tools.lib.messages` | Message text encoding. |
| `read_archive`, `file_bounds`, `read_file`, `pack_file`, `append_files`, `parse_anm`, `encode_cmpr` | `tools.lib.mpdata` | `data/*.bin` archives and sprite (ANM/CMPR) files (section 7). |
| `lz_decode`, `load_spaces`, `replace_file0`, `flag_offset(blob, space_id)`, `kind_offset(blob, space_id)` | `tools.lib.boards` | Board space (masu) tables: load, edit flags and kinds, add spaces and links. `python -m tools.scripts.masu_dump w05` prints a table. |
| `build_card`, `check` | `tools.lib.hsf_build` | Build small static HSF models (cards, the floating wheel). |
| `rebuild`, `ensure_binutils` | `tools.lib.rebuild_mdpresult` | Reassemble and relink an asm-split REL. |
| `append_tracks`, `track_from_dsp` | `tools.audio.pdt` | Append music tracks to `sound/MP6_Str.pdt`. |
| `build` | `tools.audio.thp` | Write video-only THP movies. |
| `extract_samples`, `pack_samples` | `tools.audio.musyxextract` | Sound-effect bank ↔ DSP (see `audio.md`). |

**Address catalogue:**
- `tools/lib/game.py` holds the game functions and globals that several patches share.
- `grep -rh "^FN_\|^GW_" tools/patches/` gives roughly 100 more named addresses with comments.

For example:
- `FN_ADD_COINS = 0x8017E03C` (mbCoinAddDispExec)
- `FN_COINS = 0x8015C770`
- `FN_ADD_STARS = 0x8015CF64`
- `FN_ORB_ADD = 0x8015D6FC`
- `FN_MESSAGE = 0x8016B36C`
- `FN_CHOICE = 0x8016C52C` (Yes/No)
- `FN_FLAGS = 0x80176FCC` (mbMasuMAttrGet)
- `FN_MODEL_CREATE = 0x801687F4`
- `FN_FRAMES = 0x8000E244` (wait frames)
- `GW_PLAYER = 0x80282E70` (stride `0x108`)
- `GW_SYSTEM = 0x80283290`

Reuse these rather than re-deriving them. `tools/closecall/p01_names.py` ports US symbol names onto PAL
addresses (`build/GP6P01/include/p01_names.h`), for C code.

---

## 4. DOL code space

### 4.1 The hook pattern

Replace one instruction with `b` or `bl` to a cave. The cave runs the displaced instruction,
does its work, and returns or branches back. Use only volatile registers (`r0`, `r3`–`r12`)
unless you save registers with `prologue`/`epilogue`. Record the original word in the script
(e.g. `HOOK_ORIGINAL = 0x9421FFD0`) so the patch can check it.

### 4.2 Where free space is

The DOL header has 18 section slots, numbered as the scripts do: 0–6 text, 7–17 data. Retail
fills 0–1 and 7–14. The mod adds:

| Slot | Range | Added by | Use |
|---|---|---|---|
| data 15 | `0x802F49A0`–`0x802F7DA0` (`0x3400`) | `mgtable_move` | Relocated MgDataTbl, then caves in its tail |
| data 16 | `0x802F7DA0`–`0x802F8DA0` (`0x1000`) | `castaway_spare_change` | Board event code, **full** |
| data 17 | `0x802F8DA0`–`0x802F9DA0` (`0x1000`) | `egadd_morpher` | Board event code, Unlucky Star |

New sections start at the old `__ArenaLo` (`0x802F49A0`), so the heap must start after them.
`mgtable_move` hooks `OSSetArenaLo` (`0x800994B0`) to a clamp cave at `0x80004D18`
(`lis r0,hi; ori r0,r0,lo; cmplw; bge; mr; stw; blr`). Each script that adds a section raises
the `lis`/`ori` pair to its own end, and only ever raises it. A new section 18 must start at
`0x802F9DA0`, sit in an unused slot, and raise the clamp the same way. Copy `add_section()`
from `apply_castaway_spare_change_patch.py`.

**Init area (text section 0, `0x80003100`–`0x800056C0`, TRK exception vectors).** Each
0x100-byte vector has zero padding, typically `0x8000xx18`–`0x8000xxE4`. A script's declared
limit can be larger than what it uses, so always check the bytes in the built DOL. Owners:

| Range | Owner |
|---|---|
| `0x80003600`–`0x800036E0` | bowser_bonus, bowser_bonus_fix (cave words changed between versions) |
| `0x800036E8`–`0x80003748`, `0x80003750`–`0x800037E4` | dk_bonus |
| `0x80003830`, `0x80003890`, `0x80003918`–`0x800039E4`, `0x80003A18`–`0x80003AE4`, `0x80003B18`–`0x80003BE4` | star_trap_orb (AI cave at `0x80003890`) |
| `0x80003C18`–`0x80003CE4`, `0x80003D18`–`0x80003DE4`, `0x80003E18`–`0x80003EE4` | cpu_landing (pick1, pick2, select) |
| `0x80003F18`–`0x80003F4C` | random_bonus (board-init cave) |
| `0x80003F4C`–`0x80004018` | whomp_rich (clears and rewrites the whole range each run) |
| `0x80004018`–`0x80004040` | random_bonus (trap-orb pass counter) |
| `0x80004040`–`0x800041E4` | star_shuffle_bet (select) |
| `0x80004218`–`0x800042E4`, `0x80004318`–`0x800043E4` | cpu_landing (fork2, shop) |
| `0x80004418`–`0x80004454` | cpu_landing (launch). It declares a limit of `0x800044E4` but **must not grow**: star_shuffle_bet's cave starts right after it. |
| `0x80004454`–`0x800044C0` | star_shuffle_bet (show) |
| `0x80004500`–`0x800045E4` | cpu_handicap |
| `0x80004654`, `0x80004754`, `0x80004854` (0x90 each) | whomp_rich |
| `0x80004918`–`0x800049E4` | bowser_minigame |
| `0x80004A18`–`0x80004BE4`, `0x80004C18`–`0x80004CE4`, `0x80004E00` | cpu_landing (main, fork3) |
| `0x80004D18`–`0x80004D34` | mgtable_move (arena clamp) |
| `0x80004D40`, `0x80004D80` | whatgoesup_battle |
| `0x80004F00`, `0x80005060`, `0x800050A0` (+0x40 per game) | battle_port.py (rank core, force, wrappers) |
| `0x800051B4`–`0x800051C8` | closecall_always (test aid) |
| `0x80005218`–`0x800052E4`, `0x80005318`–`0x800053E4`, `0x80005418`–`0x800054E4` | double_or_nothing |

**Dead old MgDataTbl (`0x8022FF44`–`0x80232744`).** Once `mgtable_move` has relocated the
table, its old rows are unused but **not zero**. Scripts that use this area check that the table
moved first (`section 15 address == NEW_BASE`). They also skip the zero-check, so the layout
must be tracked by hand:

| Range | Owner |
|---|---|
| `0x80230000`–`0x80230690` | wheel_of_fortune (`BASE`, `CAVES` dict) |
| `0x80230690`–`0x80230790` | luck_wheel_rewards |
| `0x802307A0`–`0x802310A0` | castaway_wheel (the E. Gadd wheel reuses its spin and random-orb caves) |
| `0x80231100`–`0x80231860` | boo_day_orbs |
| `0x80231860`–`0x802326F0` | castaway_broom |
| `0x802326F0`–`0x80232744` | free (0x54 bytes) |

**Section 15 tail (after the table, `NEW_BASE` = `0x802F49A0`):**

| Offset | Owner |
|---|---|
| `+0x2F00` | battle_ports (m603 Freeze Frame wrapper) |
| `+0x30E0` | closecall (movie path string, `0x802F7A80`) |
| `+0x3100` | daft_rafts_duel hook |
| `+0x3200` | lift_leapers_duel hook |
| `+0x3300` | duel_test_aid (test aid) |
| `+0x3340`, `+0x3360`, `+0x3380`, `+0x3390` | star_shuffle_bet (cost, payout, `"%d"`, CPU) |

**Section 16:**

| Range | Owner |
|---|---|
| `0x802F7DA0`–`0x802F8280` | castaway_spare_change |
| `0x802F82A0`–`0x802F87B0` | castaway_troll |
| `0x802F87C0`–`0x802F8D70` | egadd_wheel |
| `0x802F8D70`–`0x802F8D7C` | egadd_calamity |
| `0x802F8D80`–`0x802F8D94` | egadd_shuffle |

**Section 17:**

| Range | Owner |
|---|---|
| `0x802F8DA0`–`0x802F8FA0` | egadd_morpher |
| `0x802F8FA0`–`0x802F94A0` | egadd_robots |
| `0x802F9A00`–`0x802F9C00` | unlucky |

**Free space left:** in section 17, `0x802F94A0`–`0x802F9A00` and `0x802F9C00`–`0x802F9DA0`.
In the init area, check any padding block not listed above byte by byte. For anything larger,
add section 18.

---

## 5. Hooking REL overlays (boards and minigames)

RELs are relocatable. You can't put an absolute `bl` to DOL code in a REL. Instead, add a
**module-0 relocation**, and the loader fills in the branch:

- `bp.add_calls(rel, [(text_offset, dol_target), ...])` writes `48000001` at each site and
  appends `R_PPC_REL24` records (with an `R_DOLPHIN_SECTION 1` record first) to the module-0
  import block. That block must be last in the file. Sites already hooked to the same target
  are skipped.
- `bp.retarget_call(rel, text_offset, old, new)` changes the target of an existing module-0
  call, e.g. re-pointing a board's init tail call (`FN_INIT_TAIL = 0x8017461C`) to your cave.
- `bp.check_words(rel, text_offset, "<orig hex>", "48000001")` asserts the site is vanilla or
  already hooked.
- Text offsets are relative to REL section 1 (`text_base(rel)`). `.data` edits use the
  section 5 offset (`DATA_SECTION = 5` in `apply_egadd_calamity_patch.py`).
- Relocation types: `R_PPC_REL24 = 10`, `R_DOLPHIN_SECTION = 202`, `R_DOLPHIN_END = 203`.

**Chaining hooks.** Several patches want the same REL site. The board pass handler is
`w05Dll .text 0x2300` for Castaway and `w02Dll .text 0x3A0C` for E. Gadd. Hooks chain in a
fixed way:
1. The first patch hooks the site to its cave.
2. A later patch re-points the site to its own cave, which calls the earlier cave first.
3. The earlier script must detect the later hook and leave it alone.

Example: `castaway_wheel.patch_rel()` skips the site if it already targets
`spare.CAVE_PASS`. The chain is castaway_wheel, then spare_change, then troll. For E. Gadd's
Garage it is egadd_wheel, then robots.

**`mgtable_move` also rewrites REL relocations.** Any module-0 relocation whose addend points
into the old table range is moved to the new base. A cave in the dead old-table area that a REL
calls will therefore be moved on a re-run. `castaway_wheel` handles this by accepting
`NEW_BASE + cave - OLD_BASE` as a previous target.

**Per-step board handler.** Board RELs register a step callback (`fn_80179A0C` /
`lbl_802DE704`) that runs on every space entered, with r30 = player and r31 = space. Pass-through
events hook its common exit. Landing events hook the landing handler.

---

## 6. Message files

**Format.** `files/mess/messdata*.bin` (`messdata.bin`, `_eng`, `_fra`, `_ger`, `_ita`,
`_spa`):
- File: `u32 bank_count`, then `u32 offset[bank_count]` (relative to byte 4), then the banks.
- Bank: `u32 record_count`, then `u32 offset[record_count]` (relative to bank start + 4), then
  the records.

A message id in code is `(bank << 16) | record`. For example, `MSG_BASE = 0x330000` is bank
0x33, and `addis r4, r3, 0x33` builds an id from a record number.

**Record encoding** (`encode()` / `record()` in `apply_star_shuffle_bet_patch.py`):
- Header: e.g. `"00150003"`.
- Body: `"    "` indent, then text. Space = `0x10`, `!` = `0xC2`, `?` = `0xC3`,
  `,` = `0x82`, newline = `0x0A`, `<N>` (number argument) = `1F 01`. In the castaway scripts'
  `records()`, `'` is written as `\`.
- End: `FF 00`, padded to 4 bytes.

**Two ways to write.**
- **Own a bank:** build the bank from the pristine file, then `tools.lib.messages.write_bank(output,
  source, donor, bank)`. This splices just that bank into the current output, so patches that
  own different banks never clash.
- **Append records to a shared bank:** `edit_bank(..., bank_records=<vanilla count + earlier
  patches' records>, append=RECORDS, known_tails=...)`. `known_tails` lists every older version
  of your records, plus every combination with the records that later patches append after
  yours. That lets a re-run strip and rebuild them. Each appender sets `BANK_RECORDS` to the
  previous patch's `BANK_RECORDS + len(RECORDS)`, so the record numbers are fixed.

**Bank owners (collected from the scripts):**

| Bank | Owner | Notes |
|---|---|---|
| 5 | closecall | Minigame name (record 82) |
| 0x0E | random_bonus | Bonus Star ceremony, including minigame_wins and Unlucky Star text |
| 0x29 (41) | whomp_rich | Appends after record 9 |
| 0x2E | final_five_odds | |
| 0x30 | egadd_wheel (27–33), egadd_robots (34–42) | calamity rewrites 20; morpher rewrites 8, 9, 10, 22 |
| 0x31 (49) | star_shuffle_bet | Base 75 records; also replaces records for double_or_nothing |
| 0x33 (51) | castaway_wheel (51–58), castaway_broom, castaway_spare_change (60–68), castaway_troll (69–72) | Chained in that order |
| 0x36 (54) | star_trap_orb | Event messages (records 21, 22); orb name and description in banks 56 and 55 |
| 0x3B | boo_day_orbs | Appends records 18–24 |
| 0x3E | dk_bonus | |
| 0x3F | bowser_bonus, bowser_bonus_fix, bowser_minigame | bowser_minigame appends after the other two |
| 65 | closecall | Instructions (records 479–481) |

---

## 7. Data archives and board files

**Archives** (`data/*.bin`, via `mpdata.py`):
- Layout: `u32 count`, `u32 offset[count]`, then per file `u32 decoded_size`, `u32 decode_type`
  (7 = zlib, 1 = LZ), then the payload.
- `append_files()` adds files at the end. That's how new models (`capsule.bin`), sprites
  (`board*.bin`), Close Call models (`saf.bin`, a debug archive with 5 retail files) and the
  instruction picture (`instpic.bin`) were added.
- A data number is `(dir << 16) | index`, e.g. `MODEL_DATA_NUM = 0x00140056` is `capsule.bin`
  entry 86.
- **The US `DATA_*` directory numbers are wrong for PAL.** Use `P01_DATA_*` from
  `p01_names.py`.

**Boards.** `root/data/w0X.bin` (day) and `w0Xn.bin` (night) usually have identical space
tables, so patch both. Board numbers: `w02` E. Gadd's Garage, `w03` Faire Square,
`w05` Castaway Bay.
- File 0 is the LZ-compressed space (masu) table: `u32 count`, then per space a 46-byte record
  plus `u16` links.
- Fields: flags at `+38` (`flag_offset()`), kind at `+42` (`kind_offset()`; both offsets are within the space's record), link count at
  `+44`.
- Kinds used: 3 = green "?" action space, 4 = Miracle.
- Flags claimed by this mod (check that a flag is unused by the board REL and the DOL first):
  - `0x4000` Castaway wheel
  - `0x200000` E. Gadd wheel
  - `0x400000` E. Gadd robots' pass-only nodes
- New spaces and links (e.g. spare change guy's space 100, robots' nodes 114 and 115) are added
  with `load_spaces` / `replace_file0`.
- Always copy the original into `backups/<board>.bin.bak_before_<patch>` before the first edit,
  and never overwrite an existing backup.
- Design notes for each board, with space numbers and screenshots, are in `boards/`.

---

## 8. Minigames

- **MgDataTbl:** entries of `0x7C` bytes, terminated by `0xFFFF`. Vanilla is at `0x8022FF44`;
  after `mgtable_move` it's at `0x802F49A0`. An entry starts with `u16 overlay, u8 type, u8 flags`.
- **Types:** 0 = 4P, 3 = Battle, 6 = Duel (kettou). Flags include `MG_FLAG_RARE`, `MG_FLAG_4P`
  and `MG_FLAG_MIC`.
- **New entries in use:**
  - 82 What Goes Up (Battle)
  - 83–85 more Battle ports (`battle_ports`)
  - 86 Daft Rafts (Duel)
  - 87 Lift Leapers (Duel)
  - 88 Close Call (4P)
  The terminator follows the last entry.
- **Capacity:** `mgtable_move` says there is room for 105 entries, but section 15 caves start
  at `+0x2F00`. `0x2F00 / 0x7C` gives 97 slots including the terminator, so the **highest
  usable index is 95**. That matches the instDll index limit, which `battle_ports` raised from
  82 to 96. Move the caves and raise that limit before going past it.
- **Porting a game to another pool** (`battle_port.py`): copy the entry with a new type, then
  hook the REL so that for the new type the game takes its decathlon path (scores into
  `GwPlayer+0x2C`). `rank_core` then dense-ranks them into `+0x28` (0 = best).
- **Free Play** lists every table entry by type automatically. Its preview plays the entry's THP
  movie.
- **New minigame in C** (Close Call):
  - Source is in `src/REL/closecallDll/`. It's built outside ninja by
    `tools/closecall/build_closecall_rel.py`: mwcc GC/1.3.2, mwld GC/2.6, then `dtk rel make` **without**
    `-c config`, or dtk forces the old stub's section layout.
  - It ships as `dll/jbtestdll.rel` (overlay 5, module 1, an empty debug stub in retail), so the
    DOL's fixed overlay table is untouched.
  - `#include` `p01_names.h` first.
  - Flow uses the DOL sequencer MgSeq: `s16 timeLimit`, `u8 timerPos`, and 9 per-mode callbacks
    `(mode, frame)`.
  - Music: `pdt.py` appends tracks to `MP6_Str.pdt`, and the stream id is the track index. Use
    32000 Hz 16-bit stereo, like the retail tracks.
  - Movies: `thp.py` writes baseline 4:2:0 JPEG frames with no byte stuffing and no APP0.
  - Test aid: `apply_closecall_always_patch.py` forces board 4P minigames to entry 88.
- **Asm-split RELs** (e.g. `mdpresultdll`, `resultDll`): ninja has no assemble rule for edited
  listings. Rebuild them with `tools/lib/rebuild_mdpresult.py`.

---

## 9. Gameplay state reference

- `GwPlayer` = `0x80282E70`, `0x108` bytes per player. Fields used by the mod:
  - `+0x16` orbs landed on
  - `+0x1E` minigame coins
  - `+0x28` minigame rank / coin bonus
  - `+0x2A` minigame wins (padding, used by `minigame_wins`)
  - `+0x2C` minigame score
  - `+0x104` Unlucky Star counter (`coinGraph[51]`, unused by the game)
- `GwPlayerConf` = `0x80282E48`, `i * 0xA`; `+4` is the CPU difficulty `comDif`.
- `GwSystem` = `0x80283290` (`mgNo` = current table index).
- Coin and Star setters are `fn_8003CDA8` and `fn_8003CF28`. `apply_unlucky_patch.py` hooks
  them; see that script to tell which event is running.
- Night flag: `lha` at `0x802DDB58` (1 at night).

---

## 10. Adding a new patch

1. Read `tools/apply_all.py` (`STEPS` and its comments) and the docstrings of every script that
   touches the same file, cave area, REL site or message bank.
2. Pick code space from section 4. Prefer a cave-free edit. Grep the neighbours.
3. Write `tools/patches/apply_<name>_patch.py`:
   - The docstring says what changes, every address and REL site, the bank and records, the
     files written, and the prerequisites.
   - Import paths and helpers from the modules in section 3.
   - Check the vanilla-or-patched state at every write. Exit with a clear message if a
     prerequisite step hasn't run (e.g. "Run apply_mgtable_move_patch.py first").
   - Read the current output, else the original. Write only what you own.
   - If you append to a shared bank or archive, update the `known_tails` and backups of the
     patches before and after you.
4. Add a row to the dependency table in `tools/README.md` ("Needs" for prerequisites the
   script enforces, "Needed in game" for ones it doesn't). If you raise a
   `SystemExit("Run apply_X_patch.py first: ...")` for every hard prerequisite, a missing step
   fails loudly instead of producing a broken game.
5. Add the step to `STEPS` in `apply_all.py`:
   - It must come after everything it reads or chains on.
   - It must come before anything that rebuilds the file you write.
   - It must never come after `mgtable_move` if it runs ninja.
   - Add a comment with the reason.
   Also update the table in `tools/README.md`.
6. Test:
   - Run the script twice. The second run must report "already" and change nothing (compare
     hashes).
   - Run `apply_all.py --from <your step>` to the end.
   - From a fresh build, run `apply_all.py --only <your step and its Needs>`. That proves the
     dependency row is complete. Scripts must create their output folders: in a subset run,
     `build/GP6P01/files/<dir>/` may not exist yet.
   - Diff `build/GP6P01` against a snapshot taken before your change. Only your files should
     differ, apart from the known `w03Dll.rel` growth.
   - To prove a DOL change touches only your words, revert just those words and compare the hash
     with the pre-change DOL.
   - If you added or changed a helper in `tools/lib`, add a unit test for it in `src/tests/`
     (synthetic input from `tests/builders.py`, no game files). Then run `ruff check .` from the
     repository root and `python -m pytest` from `src/`.
7. Deploy to `root/`, rebuild the ISO with `build_iso`, and test in Dolphin (English). Dolphin "Invalid
   read/write" messages with a PC usually mean a wrong data directory, a missing appended file
   or an overwritten cave.
