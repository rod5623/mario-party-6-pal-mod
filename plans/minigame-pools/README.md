# Adding minigames to the Battle and Duel pools (GP6P01)

Status: research only. Everything below is from reading disassembly; nothing has been run in Dolphin. Items marked "inferred" or "open" are not confirmed. Addresses are P01 (Europe); DOL symbols are still generic `fn_XXXXXXXX` / `lbl_XXXXXXXX`. REL addresses are `.text` offsets in `build/GP6P01/<rel>/asm`.

Goal: put existing 4-player minigames into the Battle pool (type 3, players finish 1st-4th) and the Duel pool (type 6, two players) **while keeping them in the 4-player pool**. First candidates: **What Goes Up (m604)** and **Note to Self (m615)**, since both keep a per-player counter that can be turned into a ranking.

## Summary
- Pools are data-driven by the `type` byte of each `MgDataTbl` entry, so a game joins a pool by having a table entry of that type. `MG_FLAG_4P` is never checked by the pickers.
- To keep a game in both pools, give it a **second table entry** (same overlay, new `type`). The launcher uses the table index directly, so this works for launching. The hard part is that the table is a fixed array in the DOL (open, see Risks).
- Plain 4P games do **not** report 1st-4th. They report only a winner set. Battle games report a dense rank. Each added game needs a small REL patch that turns its own counters into dense ranks.
- m604 and m615 both have full integer counters that are still readable at game end, so Battle ranks are feasible for both. Duel (2 players) is a larger job for both.

## How the pools are built
- `MgDataTbl` at `0x8022FF44`, stride `0x7C`, ends with an entry whose ovl is `0xFFFF`. 82 real entries plus the terminator (terminator at `0x802326FC`). Type byte at +2, flags at +4. Duel (`MG_TYPE_KETTOU`, 6) has 15 games (m617, m624, m651-m663). Battle (`MG_TYPE_BATTLE`, 3) has 6 (m646, m647, m649, m664, m680, m681).
- Core picker `fn_801F19B8(type, count, out[])` (0x801F19B8) keeps an entry if: `entry.type == type`; it matches the mgPack filter; it is not `MG_FLAG_MIC`; it is not `DISABLE_DAY`/`DISABLE_NIGHT` for the current time; and it is not in the per-type recent-history ring. If too few pass it tops up from the ring, then shuffles.
- Duel: Duel space `fn_801B920C` -> `fn_801F4ECC` -> `fn_801F0BCC(6, 0)` (3 choices) -> `fn_801F5854`.
- Battle: `fn_801EF728` -> `fn_801F2F5C` (bet) -> `fn_801F19B8(3, 3)` -> `fn_801F5854`. The odds patch (`tools/patches/apply_minigame_odds_patch.py`) already lets Battle trigger after any roll type at 18%.
- History rings are fixed length (Battle 2, Duel 14), so adding games is safe; with few eligible games the top-up can repeat recent picks.
- Hazard (inferred, untested): for a 1v3 or 2v2 roll, `fn_801F008C` has already written team `grpNo` values (0/1). `fn_801F2F5C` does not reset them. With the odds patch, a Battle can follow such a roll. Battle RELs may expect `grpNo` to be the player index.

## What each game type reports
Shared structures: `GwPlayer` at `lbl_80282E70`, stride `0x108` (`+0x24 coinBattle`, `+0x26 mgCoin`, `+0x28 mgCoinBonus`, `+0x2C mgScore`). `GwPlayerConf` at `lbl_80282E48`, stride `0xA` (`+6 grpNo`). Flags: `0x1000F` practice, `0x30002` decathlon (checked with `fn_8006A7B0`).

| Type | Winner set (`fn_80072388`) | `GwPlayer+0x28` | Full order? |
|---|---|---|---|
| 4P / 1v3 / 2v2 / Duel | yes, up to 4, ties = several winners | 10 for winners | **no** |
| Battle | not called | dense rank, 0 best, ties share | yes |

- `fn_80072388(p0..p3)` (-1 = empty) only drives the win/draw banner and jingle. `fn_800723E0` reports a draw.
- Battle example: m646 `fn_1_9118` (0x9118-0x937C) sorts 4 {player, score, rank} records, writes dense rank into `+0x28`, and writes the score to `+0x2C` in decathlon. If the top score is 0 it leaves everyone at rank 3.
- Consumers:
  - `fn_8020CDD4` (board coin award) pays type 3 only when `+0x28 == 0`. Other types pay if `+0x26 + +0x28 > 0`.
  - `resultDll` `fn_1_A0` shows the result screen for types 0-3, 5, 8. Type 3 uses `fn_1_7D04`. `fn_1_37D8` ranks by `+0x28`; `fn_1_40F0` splits the pot (sum of `coinBattle`).
  - Battle pot shares by rank pattern: (0,1,2,3) 70/25/5/0%; (0,0,1,2) 50/50; (0,0,1,1) 50/50; (0,0,0,1) 30x3; (0,1,1,2) 60/20/20; (0,1,1,1) 70/10/10/10; (0,1,2,2) 70/30; (0,0,0,0) 25x4. Index-to-share mapping for the three-way patterns not fully verified.
  - Duel (`fn_801BB0D0`): winner is the duelist with `+0x28 > 0` while the other has 0; both zero or both positive is a draw. Duelists get `grpNo` 0/1; everyone else gets `grpNo` 2 (`fn_801B920C`).
- Correction: the "Dunk Bros result investigation" in `src/README.md` is stale. `fn_801F5854` is the minigame launcher, not a result reader; `lbl_80282E48 + 0x06` is `grpNo` (resultDll `fn_1_A0` overwrites it each result screen); and the built `m699Dll` `fn_1_50C` already calls `fn_80072388` and writes `+0x28 = 10`.

## Candidate: What Goes Up (m604)
- Table entry: `include/mgdata.inc` (`DLL_m604dll`, 4P, `HAS_NIGHT|4P|PACK_WEIRD|PACK_ACTION`). C++ game (`patapata.cpp`) with a day and a night mode (`lbl_802DDB58`).
- Counter: s32 score per player at `player_obj+0x8C`. Objects are in a list rooted at `lbl_1_bss_24`; player index at `+0x14`. Score = `(int)((Y + 50.0) / 100.0)`, recomputed every frame (day `fn_1_105D8` 0x11534, night `fn_1_12D48` 0x13CCC).
  - Day: higher is better. Night: lower is better, and reaching 0 ends the game (everyone at 0 ties, no arrival tiebreak).
  - Readable from end of play until overlay teardown (`fn_1_66AC`).
- End of game: main thread `fn_1_6AE4`. `fn_1_73A4` finds winners (all players tied on the best score; in night, nobody at 0 is a draw). Win banner via `fn_1_18EA0`. Both normal and decathlon paths join at the `bl fn_1_1914C` at 0x6D80.
- Writes to `GwPlayer`: only in the singleton destructor `fn_1_1876C` (`+0x28 = 10` per winner, 0x1884C, skipped in practice) and the decathlon path `fn_1_7534` (`+0x2C = score`, 0x75D8). **`fn_1_1876C` already skips the winner write when `MgDataTbl[mgNo].type == 3`** (0x187B8-0x187C0). There is no skip for type 6.
- Battle patch sketch: redirect the `bl fn_1_1914C` at 0x6D80 to a new function. For type 3 or 6, and not practice, dense-rank the scores (descending in day, ascending in night) into `GwPlayer+0x28`, copying m646 0x9264-0x9314. For type 6 also clear the four winner slots at `bss_38+4..0x10` (or add a type 6 skip next to the type 3 one). If nobody reaches 0 at night the original result is a draw; ranking by remaining height is a design choice.
- Start/finish messages (`fn_80044488`) are remapped by `MgDataTbl[mgNo].type`, so a Battle or Duel entry changes which message class is used. Whether those accept the same arguments is unverified.
- Duel: all loops fixed at 4, `grpNo` never read, one shared camera. Players with `grpNo` 2 would still spawn (inferred), so a duel needs participation filters.

## Candidate: Note to Self (m615)
- Table entry: `DLL_m615dll`, 4P, `HAS_NIGHT|4P|PACK_ACTION|PACK_WEIRD|PACK_EASY`, index 14. The mechanic (send a note out and have it come back to you) is inferred from behaviour. Fixed 30 s, no early end.
- Counter: `bss_1C[4]`, s32 per player index, higher is better, capped at 99, never zeroed. Incremented only in `fn_1_BCE8` (0xC144-0xC190). Still intact at game end, and read by the HUD (`fn_1_D2D8`).
- End of game: `fn_1_99D0` (0x99D0, asm lines 10504-10672), runs until `fn_800721FC() == 6`.
  - Max score loop; `bss_C[i] = 1` if the player ties the max, else -1; all 0 if max is 0 (`bss_C` also drives the winner pose and camera; keep it).
  - Winner loop: collects charNos, writes `GwPlayer[i]+0x28 = 10` (0x9B5C, unless practice).
  - Decathlon: writes `+0x2C = score` for all four (0x9BAC).
  - Otherwise calls `fn_80072388` (0x9BE0); the REL's only call. It never calls `fn_800723E0`.
- Type awareness: **none**. The REL never reads `GwSystem` or `MgDataTbl`.
- Battle patch sketch: replace the winner-collection loop and the `fn_80072388` call with a dense-rank loop writing `GwPlayer+0x28`, reusing the `mulli 0x108` + `lbl_80282E70` + `sth 0x28` pattern at 0x9B4C-0x9B5C. Because both table entries share the REL, branch on the entry type at that point: `lhz GwSystem+0x38 ; mulli 0x7C ; add MgDataTbl ; lbz 2 ; cmplwi 3` (same as resultDll 0x470-0x494). Decide whether an all-zero game should give everybody rank 3 as m646 does.
- Duel: one shared camera, but all loops are fixed at 4. Player objects spawn from `GwPlayerConf`; with duel `grpNo` {0,1,2,2} the slot mapping falls back to identity, so all four play. Restricting to two needs edits in the creation code (`fn_1_9620`, `fn_1_DA90`, `fn_1_D118`) and in `fn_1_99D0`, `fn_1_BCE8`, `fn_1_CBD0`, `fn_1_F938`.

## Design: a second table entry per mode
- Keep the existing 4P entry unchanged. Add a new entry with the same `ovl` (and instruction pictures, movie and text), `type = MG_TYPE_BATTLE` (or `KETTOU`), and a Battle-appropriate flag set. The REL branches on type at the end-of-game point.
- The launcher `fn_801F5854(type, idx)` stores `idx` directly in `GwSystem.mgNo` and does not call `MgNoGet`, so launching the new entry is fine.
- `MgNoGet(ovl)` (`src/game/mgdata.c`, DOL `fn_8006A108`) returns the **first** match, so these see the 4P entry instead of the new one: instruction and pause text (`gamemes.c:783`), practice-exit type (`gamemes.c:1071`, so a Duel practice screen would accept any pad, not just `grpNo < 2`), and Free Play/menu lookups (`mgmfreedll`, `selmenuDll`). `gamemes.c:1147` and `objsysobj.c:133,178` only compare against -1 and are harmless.
- `GameMesCreate` (`fn_80044488`) uses `GwSystem.mgNo`, so the new entry's type is honoured for start/finish messages.

## Risks and open questions
1. **Table size.** `MgDataTbl` is a fixed array in DOL `.data`. Not yet checked: what follows it in memory, where new entries can go, and every reference (`lis/addi` pairs, `lbl_80269070` history lists, `lbl_802691BC`, `lbl_80269408`, `fn_801928BC` category lists of 32, `mgmfreedll`, `selmenuDll`). The unlock bitfield (`mgUnlock`, 128 bits for ids 601-728) and `GwSingleMgFlag` (96 bits; ids >= 697 ignored) limit new ids.
2. Behaviour of the start/finish banners for type 3/6 inside a REL written for 4P (m604 uses them; m646 makes no `fn_80044488` calls).
3. Whether `resultDll` `fn_1_7D04` presents m604 and m615 ranks correctly.
4. Stale `grpNo` before Battle (see hazard above) in a 4P REL; m604 and m615 both fall back to identity only if some group is missing.
5. Duel restriction to two players for 4P RELs (camera appears shared in both; creation and scoring loops need filters).
6. m604 night-mode tie handling and m615 all-zero handling for ranks.

## Suggested order
1. Locate and plan table growth (question 1); this blocks everything else.
2. Prototype m604 Battle (its REL already knows type 3).
3. m615 Battle.
4. Duel versions after the Battle path works.
5. Test in Dolphin, including a Battle after a 1v3/2v2 roll.

## Table growth investigation
Findings (checked against `orig/GP6P01/sys/main.dol`):
- **No room to grow in place.** The 0xFFFF terminator entry spans `0x802326FC-0x80232777` and unrelated data (`lbl_80232778`, float tables) starts immediately after. Every new entry means relocating the whole table (82 entries + new ones + terminator, about 0x7C x 90 = ~11 KB).
- **No dead space in the DOL.** The DOL has no spare data slot with free memory behind it: sections 15-17 and text slots 2-6 are unused header slots, but the only >1 KB zero runs in data (e.g. `0x80235324`, `0x802366a8`, `0x8023c83c`) are 0x400-0x7C5 bytes and are probably zero-initialised tables in use. The TRK-vector code caves used by earlier patches are far too small. The BSS (`0x80269ec0`, 0x78ace bytes) is not file-backed.
- **References to patch when relocating** (all use `lis/addi` on `lbl_8022FF44`):
  - DOL: roughly 35 pairs (text `auto_03_80005920` at 0x80044550, 0x80045B38-0x80045BD0, 0x80046540-0x80046554, 0x8006A114; `auto_03_800EF6C8` at 0x80192914-0x80195D94, 0x801F1118, 0x801F1AAC-0x801F3CD8). Includes the type read in `fn_801F19B8` and `fn_8020CDD4`.
  - RELs (patch the relocation addend, not an instruction): `instDll`, `mdsingdll`, `mgmbattledll`, `mgmbingodll`, `mgmfreedll`, `mgmrenshodll`, `mgmtournamentdll`, `optionDll`, `resultDll`, `selmenuDll`, a pointer in `.data` of `mgmdecathlondll`, plus 22 minigame RELs (m603, m604, m605, m610, m611, m622-m624, m628, m634, m639, m648, m652-m655, m671-m673, m677, m681), each with one HA/LO pair (the `GameMesCreate`-style type check).
  - Counts of 2 in each minigame REL mean one `lis/addi` pair each.
- **Where could ~11 KB go?** Not yet decided. Candidates:
  1. Add a new DOL data section (slots 15-17 are free) at a high address. Risk: the arena/heap start may be derived from the end of the DOL, so memory behind the new section could be overwritten by the heap. Needs checking in `OSInit`/`__start` and testing in Dolphin.
  2. Find a large dead block in the DOL (unused library functions or debug data) to host the table.
  3. Shrink the problem: only the table entries used by the pickers need the new location, but every consumer indexes the same base, so this does not help without more code changes.

### Heap / arena check (result: a new DOL section is workable)
Confirmed from `OSInit` (`0x80097988`, asm `auto_03_80005920_text.s` ~165100-165200) and `build/GP6P01/ldscript.lcf`:
- Memory layout comes from the linker script: `_stack_end` = end of `.sbss2`; `_stack_addr` = `_stack_end` + 0x10002 (rounded to 8); debug stack = `_stack_addr` .. +0x2000; **`__ArenaLo` = end of the debug stack, 32-aligned (`0x802F49A0`)**; `__ArenaHi = 0x81700000`.
- `OSInit` sets ArenaLo in two ways, both through `OSSetArenaLo` (`0x800994B0`, which is just `stw r3, __OSArenaLo; blr`): the value in `BootInfo+0x30` if the loader set it, else the linker constant `__ArenaLo` (`lis/addi` at `0x80097AA0/AA4`). A debug-flag path (`0x80097AD8`) can set it to `_stack_addr` instead. `__OSArenaLo` starts as `0xFFFFFFFF` in the DOL data.
- The boot memory setup (around `0x8000AB5C-0x8000B068`) and `fn_800994B8` (alloc-from-ArenaLo) always call `OSGetArenaLo` then `OSSetArenaLo(old + size)`, so they only ever raise it. The game heaps start from ArenaLo.
- So **the DOL end does not decide the heap start**. A new section placed at `0x802F49A0` (the vanilla ArenaLo) would be overwritten by the heap unless ArenaLo is raised past it.
- **Safe plan:** patch `OSSetArenaLo` (two instructions, 8 bytes) to branch to a small cave that clamps: `lis r0,hi(END) ; ori r0,r0,lo(END) ; cmplw r3,r0 ; bge L ; mr r3,r0 ; L: stw r3,__OSArenaLo ; blr`, where END = new table end rounded to 32. It covers the `BootInfo`, linker-constant and debug-stack paths with one patch, and later callers (which only increase ArenaLo) are unaffected. The cave can live with the other caves in the TRK vector padding (earlier patches use `0x80003830-0x80003B18`; pick an unused spot and verify it is zero).
- Add the table as DOL data section slot 15 (header file offset `4*15`, address `0x48 + 4*15`, size `0x90 + 4*15`), appended at the end of the file with a 32-byte aligned file offset. The existing scripts patch the built `main.dol` after the fact (see `tools/apply_*_patch.py`), so this fits their flow.
- Still unverified: whether Dolphin and the retail apploader load an extra section above the BSS/stack range as expected (the DOL header describes it like any other data section), and whether anything else reserves `0x802F49A0+` early. Needs a Dolphin test with a trivial section first.
- Still open: whether DOL sections beyond the original DOL range cause trouble for real-hardware loaders (not a concern for Dolphin testing).

## Table move proof of concept: `tools/patches/apply_mgtable_move_patch.py`
Status: script written and run on `build/GP6P01/main.dol`; **not yet booted in Dolphin**. It moves the table without adding entries, so the game should behave exactly as before.

What it does:
1. Adds DOL data section slot 15 at `0x802F49A0` (the vanilla ArenaLo), size `0x3400` (105 entries; 82 used), holding a byte copy of the table (currently including the Dunk Bros edits). The old table stays in place, unused by the DOL.
2. Retargets the DOL's references: 152 `lis`/`addi` operands (76 pairs), found from the `lbl_8022FF44@ha`/`@l` lines of the asm listings and checked against the bytes (it aborts if an operand is not the expected old value). One `b lbl_8022FF44` at `0x802141DC` is a data word that disassembled as a branch; it is not retargeted.
3. Patches `OSSetArenaLo` (`0x800994B0`) to branch to a cave at `0x80004D18` that stores `max(value, 0x802F7DA0)`, so the heap starts after the section.
4. Writes patched copies of every REL that imports the table into `build/GP6P01/files/dll/` (230 relocation addends in 32 RELs: `instDll`, `mdsingdll`, `mgm*dll`, `optionDll`, `resultDll`, `selmenuDll`, 22 minigame RELs; `mgmdecathlondll` also has 9 data pointers into the table interior).
   Only the addend word of each relocation changes (checked for m604).

Order and caveats:
- Run it **last**, after the other `apply_*_patch.py` scripts. `apply_dunk_bros_patch.py` edits the old table and ninja rebuilds `main.dol` from asm, either of which would undo or bypass this patch. Re-running is safe (it detects section 15 and does not overwrite the new table). Future table edits must target `0x802F49A0`, not `0x8022FF44`.
- Deploy: replace `&&systemdata\Start.dol` with `build\GP6P01\main.dol` and copy `build\GP6P01\files\dll\*.rel` over the extracted `files\dll\`. All patched RELs must be deployed with the new DOL; the original RELs would still read the old table.
- `dtk dol info` fails on this DOL with an "Unpaired epilogue" error at `0x801C8068` (the Star Trap hook area), not related to this patch.
- The asm listings do not know about the new section; a fresh `ninja` build of `main.dol` drops this patch.

Dolphin test to confirm:
1. Game boots, board starts, a minigame plays (the vanilla table is unchanged).
2. Instruction screens, Minigame Mode lists and the result screen still work.
3. Heap sanity: a long session across several minigames with no crash.

## Battle copy of What Goes Up: `tools/patches/apply_whatgoesup_battle_patch.py`
Status: applied and deployed to `root` (Start.dol + `dll/m604DLL.rel`); **not yet tested in Dolphin**. Run it after `apply_mgtable_move_patch.py`.

- **Table:** entry 82 in the relocated table (`0x802F7158`) is a byte copy of m604's entry with `type = 3` (Battle); the terminator moved to entry 83. The original 4P entry (index 3) is unchanged, so What Goes Up stays in the 4-player pool.
- **REL hooks** (no REL code is rewritten; two module-0 relocations are appended to `m604DLL.rel` and call DOL code):
  - `fn_1_6AE4` +0x6D0C (`lwz r0,0x374(r31)`) -> `bl hook_a` at `0x80004D40`. For a type-3 entry it returns 1, so the game takes its decathlon path. That path (`fn_1_7534`) copies each player's score into `GwPlayer[i]+0x2C` and skips the winner banner and the "+0x28 = 10" write.
  - `fn_1_6AE4` +0x6D80 (`bl fn_1_1914C`) -> `bl hook_b` at `0x80004D80`. For a type-3 entry, outside practice, it dense-ranks the four scores into `GwPlayer[i]+0x28` (0 = best, ties share, same as other Battle games), zeroes `+0x2C` unless decathlon, then jumps to `fn_1_1914C` using the return address (target = LR + 0x123C8).
  - Day: higher height wins. Night: lower wins (the "reached 0" winners rank first).
- Ranks are not recomputed when nobody reaches 0 at night: they follow remaining height instead of the original "draw".
- No "winner" banner plays for the Battle version (matches other Battle games). Start and finish messages use the Battle message class because they follow the table type; this is the main thing to watch in Dolphin.
- Checked by running both hooks' bytes in a small PPC interpreter: day `[5,3,5,0]` gives ranks `[0,1,0,2]`, night gives `[2,1,2,0]`, all-zero gives all 0, type 0 and practice leave the game unchanged, and the tail jump lands on `fn_1_1914C`.
- **Dolphin test list:** (1) Minigame Mode and the normal 4P pool still show/play What Goes Up. (2) Trigger a board Battle (odds patch makes it 18% after any roll) until What Goes Up is offered; check the intro banner, play, then the rank screen and pot split. (3) Check day and night variants. (4) Check that a Battle after a 1v3/2v2 roll still plays correctly (stale `grpNo` hazard).
- Not done: Duel version of What Goes Up (needs a 2-player restriction).

## More Battle copies: `tools/patches/apply_battle_ports_patch.py` (with `tools/lib/battle_port.py`)
Status: applied and deployed to `root`; **not yet tested in Dolphin**. Run after `apply_mgtable_move_patch.py` and `apply_whatgoesup_battle_patch.py`; safe to re-run. `apply_unlock_all_patch.py` makes the new entries selectable in Minigame Mode.

Each game gets its own type-3 entry sharing the 4P overlay (4P entries untouched). A shared routine `rank_core` (DOL cave `0x80004F00`) reads each player's score from `GwPlayer[i]+0x2C`, and for a type-3 entry that is not a practice game writes dense ranks (0 = best, ties share) into `GwPlayer[i]+0x28`, then clears `+0x2C` unless this is a real decathlon. Hooks are module-0 relocations in the REL, so no REL code is rewritten.

| Table index | Game | Score | Hook (REL .text offset) | Notes |
|---|---|---|---|---|
| 82 | m604 What Goes Up | `player_obj+0x8C`, day high / night low | `0x6D0C` and `0x6D80` (see earlier section) | uses the game's decathlon branch |
| 83 | m615 Note to Self | `bss_1C[4]`, higher | `0x9B74` (decathlon check, call retargeted to `force_deca` at `0x80005060`) and `0x9BE4` (wrapper at `0x800050A0` runs `rank_core(0)` then the displaced `lha r0,4(r30)`) | decathlon branch writes `+0x2C`; the "+0x28 = 10" winner write earlier is overwritten by the ranks |
| 84 | m614 Cannonball Fun | work struct `+0x17C` (hits, first to 5 wins), player index at `work+4`, work pointers at `0x34(r1)` in `fn_1_656C` | `0x7770` (`bl fn_80072388` retargeted to a hook at `0x80005100`) | no decathlon branch; the hook copies the counts to `+0x2C`, ranks, and returns without the winner banner |
| 85 | m603 Freeze Frame | score object (REL `bss_10`, in r24) `+0x24 + i*0x1C`, higher | `0x92C` (`bl fn_8004944C` fade call retargeted to a hook at `0x802F78A0` in the tail of the table section) | winner decided earlier by `fn_1_62DC` (0x87C); the REL already skips "+0x28 = 10" for type 3 |

- All hook code was run in a small PPC interpreter against the real bytes: ranks match for ties and out-of-order player indices, type 0 entries and practice leave the game unchanged, and r1/LR/r3-r5 are restored where required.
- Open points for Dolphin: (1) Note to Self skips the winner banner, Cannonball Fun skips it, but **Freeze Frame still shows its winner/draw banner** (message class follows the table type; check it displays); (2) Cannonball Fun's timeout path (inferred: highest count wins, ties share); (3) Freeze Frame awards points during the result reveal, and the ranking runs after that (confirmed in the code order, not timed).
- Free space: the init-section caves are almost full (`0x800051B4-0x800051E4` left). The relocated table section (`0x802F49A0`, 0x3400 bytes) holds the table from the start and the Freeze Frame hook at `0x802F78A0`; the table can grow to 97 entries (index 96) before it would reach that hook, and about 0x400 bytes remain after the hook for more caves.

## Battle roulette crash and thumbnail table: `tools/patches/apply_battle_thumbs_patch.py`
Symptom (Dolphin, party mode as the Battle choices appear): `Invalid read from 0x3bf57ab0, PC = 0x80009114`. `0x80009114` is the data-directory loader (`fn_80008DD4`), reading with a garbage file index.

Cause (confirmed in the asm, not yet re-tested): the Battle choice screen `fn_801F3C4C` finds each choice's thumbnail and title by matching its name message (`MgDataTbl` entry `+8`) against a **6-row table at `0x8021AA58`** (stride 0xC: name message, night thumbnail, day thumbnail; rows for m646, m647, m649, m664, m680, m681; thumbnails are files `0x5009E-0x500A5`). The same row also supplies the title text (`fn_8016B7A4(row.name)` at `0x801F3E68`). A game with no row ends the search loop at row 6, which is the next table in memory, and the loader gets garbage.

Fix: the table is copied to `0x802F79A0` (relocated section, 10 rows), rows for the four added games are appended (title message plus placeholder thumbnails reused from rows 0-3), the four `lis/addi` references (`0x801F3CB8`, `0x801F3D18`, `0x801F3D4C`, `0x801F3E58`) are retargeted, and the loop bound at `0x801F3CF0` changes from 6 to 10.

- The new games show **another Battle game's thumbnail** (m604 uses m646's, m615 m647's, m614 m649's, m603 m664's) with their own title text. Real thumbnails need new image files in the data directory (or the instruction pictures `INSTPIC_ANM_m6xx`, which have not been tried here).
- The missing rows crash whenever a new game is offered, independent of the unlock patch. Other per-Battle-game tables may exist (`lbl_8021AAA0` and `lbl_8021AAC0` are used by `fn_801FA3EC` and `fn_801FCCC0`; not examined), so further crashes on the Battle result or later screens are possible.

## Wrong game launched (Smashdance) for the added entries: instDll index clamp
Symptom: the Battle choice screen showed "Note to Self" (table index 83) but Smashdance (index 0) started.

Cause (confirmed in the asm, not yet re-tested): the instruction-screen overlay `instDll` (run before every board minigame) reads `GwSystem.mgNo` and does `cmplwi r3, 0x52 ; blt ... ; li r4, 0 ; sth r4, bss_36` (REL .text `0x128`), i.e. any table index of 82 or more becomes 0. It then uses entry 0 for everything (instructions, overlay, `dataDir`). Smashdance was never in the Battle pool; it was the clamp target for all four added entries (82-85).

Fix: `apply_battle_ports_patch.py` now patches that compare to `0x60` (index limit 96) in the patched `instDll.rel`. Other `0x52` compares found in the DOL and RELs (`fn_800B88F0`, `fn_800B8B90`, `fn_800ED854`, `fn_801928BC`, `m617dll`, `m663dll`, `mdmicdll`, `mgmrenshodll`) were not examined; `mgmrenshodll` and `fn_801928BC` loop over the minigame table and may have a similar limit.

## CPU choice in the Battle roulette
Confirmed from `fn_801F3C4C` (0x801F3C4C): each CPU player keeps a target slot `+0xE = random(choice count)` (`fn_8014CD78`, uniform) and re-rolls it about once every 64 frames (`fn_8003FBE4 & 63 == 0`); the cursor then moves toward it. The final vote of every player is tallied, the slot with most votes wins, ties are broken at random (`0x801F4974`). There is no per-game weight, so the CPU does not prefer any game. The order of the three offered games is shuffled by the picker (100 random swaps in `fn_801F19B8`), and all eligible games (right type, pack, day/night, not in the 2-entry recent history) are equally likely to be offered, so the four added games are on the same footing as the six vanilla ones.

## Thumbnails: `tools/patches/apply_battle_thumbs_patch.py`, `tools/lib/battle_thumbnails.py`, `tools/lib/mpdata.py`
Status: applied and deployed to `root` (`&&systemdata/Start.dol`, `data/board*.bin`); **not yet tested in Dolphin**. Preview of the generated art: `new_thumbnails_preview.png`.

- Format (confirmed by decoding): the Battle thumbnails are files `0x9E-0xA5` of `data/board.bin` (data directory 5). Each is a zlib-compressed (type 7) sprite (ANM) with one 128x128 CMPR bitmap (octagonal blue/white frame, transparent corners, picture inside). The archive is `u32 count, u32 offsets[count]`, each file `u32 size, u32 type, [u32 size, u32 compressed size], data`.
- The six language variants (`board`, `board_fr`, `board_ge`, `board_it`, `board_sp`, `board_us`) all contain the same 176 files, so the same 8 new files (indices 176-183) are appended to all of them. All original files are unchanged.
- New art: for each added game the day and night instruction pictures (`instpic.bin`, 256x256 CMPR) are scaled to 96x96 and composited into the frame of thumbnail `0x9E`; blocks that do not touch the picture opening are copied byte-for-byte from the original frame. The CMPR encoder (`mpdata.py`) is a simple principal-axis one, so the picture is slightly softer than the originals.
- The DOL table (`0x802F79A0`, rows of name message, day file, night file) now points the four new rows at files `0x500B0-0x500B7` (m604 day/night, m615, m614, m603). Day is `+4`, night `+8`, selected by the board's night flag.
- To replace any thumbnail with your own art: edit `battle_thumbnails.py` (it builds from `instpic.bin` now) or supply 128x128 RGBA PNGs and encode them with `mpdata.encode_cmpr` into the same ANM template.

## Excluding minigames from party mode: `tools/patches/apply_minigame_exclusion_patch.py`
Status: script run on `build/GP6P01/main.dol` with an empty list (only the two mask patches applied); **not yet tested in Dolphin**. Run after `apply_mgtable_move_patch.py` and `apply_battle_ports_patch.py`; safe to re-run.

- List the games in `tools/excluded_minigames.txt`: `m604` (every table entry with that overlay) or `m604:3` (only that type: 0 4P, 1 1v3, 2 2v2, 3 Battle, 6 Duel). The table `ovl` field is the minigame number minus 595.
- The patch sets new flag bit `1<<12` (`PARTY_EXCLUDE`) on the matching entries of the relocated table. The picker `fn_801F19B8` already rejects `MG_FLAG_MIC` in its first pass (`0x801F1AF8`) and in the history top-up (`0x801F1C48`); both `rlwinm r0,r0,0,22,22` become `andi. r0,r0,0x1200`, so excluded games are never offered or topped up.
- Minigame Mode and Free Play do not test the bit, so they still list excluded games. Pickers that bypass `fn_801F19B8` (Bowser, DK, other special rolls) are not checked yet.
- The script warns if a type pool falls below its pick count (Battle and Duel offer 3).
