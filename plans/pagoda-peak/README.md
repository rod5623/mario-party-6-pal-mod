# Pagoda Peak port: handoff for the next session (updated 2026-11-25, end of the third session)

**Start here:** read "Next session" just below, then "Where things stand". The third session gave Pagoda Peak
its own archive, message bank, orb list and results label (steps 2a-2c) and added MP7's **Cannon orb**
(2c-bis), which the user is happy with. The next big job is **2d, a real 7th icon on the party board select**
(research first, then a layout decision with the user), after a few quick checks and Cannon tidy-ups.

Goal: add Mario Party 7's **Pagoda Peak** to this MP6 PAL mod as a **7th party board** (board 11),
played by MP6's rules: MP7's map, spaces, Star and events, running on MP6's engine. The board runs a
**board REL written in C** (Route B; Route A was ruled out, see Experiment 2 below). Experiments 1 and
2 at the end are the research record: read their "Result" sections, not their plans.

Paths below are relative to `src/` (where the commands run) unless they start with `plans/`, `root/` or
`backups/`. The C sources are in `src/src/REL/w07Dll/` from the repository root. Work is on git branch
`pagoda-peak`. The user commits; Claude never runs git add, commit or push. The general recipe for adding
another board, drawn from this port, is `src/docs/adding-a-board.md`.

## Next session

Do these in order; each ends with the user testing in Dolphin, and only what the user confirms counts.

1. **Quick checks to ask the user about** (all built and deployed, not yet confirmed):
   - A player reaching a **broken bridge** (step 1 below): hop back, move ends, repaired next turn.
   - **2c:** Pagoda Peak's shop never offers the Snack orb (other boards still do); the party results screen
     after a Pagoda Peak game shows the "Pagoda Peak" label (other boards' labels unchanged).
   - **Cannon CPU use** (2c-bis stage 3): a CPU using the Cannon (Dolphin log "Cannon orb, player n from space a
     to b"), and never on space 43. The user said they're happy with the Cannon, but didn't mention CPUs.
   - **Snowflake Lake itself** on its vanilla archives and bank: page 1's Snowflake Lake icon launches it again
     (`clone_board_menu` is gone).
2. **Cannon tidy-ups: built and deployed in the fourth session (2026-11-25), not yet tested in Dolphin.** The user's
   choices:
   - **Odds:** weight 15 in all 12 columns (`CANNON_WEIGHTS`): the other orbs total about 100 per column, so
     about 13% per pick, like Mushroom or Warp Pipe. Price stays 10.
   - **Logging:** only the one line "Cannon orb, player n from space a to b" is left.
   - **Part 3, MP7's explosion gag** (space 43, nowhere to go), `cannon.c` `Explode`, from MP7 `0x801A988C`-`0x801A9BC4`:
     the player is shot up 1000 and falls back into the barrel (45 frames), 60 frames inside, the cannon shakes
     60 frames (rotX/Z +-10t sin 1440t, recoil looping), then `FILE_CANNON_BOOM` at 1.5 size, 75 up and 50 back;
     10 frames on the cannon vanishes, 5 later the player is back on the space in the stun motion (MP6 6) for 60
     frames. MP7 plays motion 11 there and its own sounds. **To check:** use the Cannon on space 43.
   - **Sounds:** left for the polish step (the user's choice). MP7's ids: `0x443` into the cannon, `0x444` fire,
     `0x448` the fuse while it shakes, `0x323` the explosion.
3. **2d, board select page 2: built and deployed in the fourth session (2026-11-25), not yet tested.** New step
   `party_pages` (after `minigame_wins`; `tools/patches/apply_party_pages_patch.py`, its docstring has every hook)
   rebuilds `mdpartydll` from its asm with page code inside the REL: the cursor stays a slot 0-5, a page number
   picks what the six slots show by rewriting their entries in the menu's own tables (icon textures, half-disc
   sprites, banner bank, unlock flags, DLL table); the cursor walks over existing boards only, across pages and
   wrapping. `clone_board` now hooks that REL. `pagoda_board` writes `mdparty.bin` files 254-257 (empty-slot icon,
   Pagoda Peak's icon and half-disc, from the user's render in `src/orig/pagoda_screens/`, `tools/pagoda/select_art.py`),
   slot 0's banner files' bank 1 (MP7 lettering) and bank 2 record 15 (MP7's select line). The aid
   `clone_board_menu` was deleted on 2026-11-26. **To check in Dolphin:** page 1 unchanged and Snowflake Lake launching Snowflake Lake
   (also the open Snowflake replay check); right from Clockwork Castle shows page 2 (Pagoda Peak + 5 "?" icons, its
   banner, description, half-disc); right from Pagoda Peak wraps to Towering Treetop, left from Towering Treetop
   goes to Pagoda Peak; picking it plays Pagoda Peak; "play again" after the game starts Pagoda Peak again; backing
   out of the rules screen while on page 2. **First test (2026-11-26):** invalid reads in `memcpy` (PC 0x8000357C, from 0xAF downwards) right after picking party mode: the extra RGB5A3 textures (about 790 KB, loaded when the menu opens) left no room for the character models (`Hu3DModelLink` copying a model that failed to load). Fixed the same day, not yet retested: the new pictures are C8 (the empty-slot icon 128x64) and the vanilla half-discs 0x04-0x11 re-encoded as C8, so the menu now loads about 600 KB less than vanilla. If it still fails, look for `HuMem>memory alloc error` in Dolphin's log. **Second test (2026-11-26):** party mode opens, page 2 shows (Pagoda Peak icon, 5 "?" icons, the description); but the banner stayed "Towering Treetop" with invalid reads in HuSprCall (HuSprBankSet takes group, member, bank: it was called with a sprite id), and picking Pagoda Peak started Snowflake Lake (the launch indexes the DLL table by the board number aliased 11 -> 3, not the cursor). Both fixed the same day. **Retest (2026-11-26): confirmed by the user.**
4. ~~**2e, promote `pagoda_stub` into `pagoda_board`**~~ Done (2026-11-26): `pagoda_board` builds and installs the
   REL (`install_rel`) and the character motions (`write_char_motions`, build output only); the build files came out
   byte for byte the same. The aid is retired to `plans/pagoda-peak/retired/`.
5. **Polish** (step 3 below), in whatever order the user picks.

## Where things stand

Board 11 is a slot cloned from Snowflake Lake (board 3). Step `pagoda_board` (last in `STEPS`) gives it **its own
archive `w07.bin` (data dir 261), message bank 0x4B, orb list and results label**, and the **Cannon orb** (orb id
8). It also builds the **C board REL** and adds the extra character motions. It still borrows Snowflake Lake's sound
group, and its save records count under Snowflake Lake (the user's choice). The board select reaches it on page 2
(`party_pages`).

**Shipping a change** (from `src/`, then copy into `root/`, then `python -m tools.scripts.build_iso`):
- REL (`src/REL/w07Dll/*.c`) or anything else of `pagoda_board`: `python tools/apply_all.py --from pagoda_board`
  (the last step), then copy `build/GP6P01/main.dol` to
  `root/&&systemdata/Start.dol` and the changed ones of `files/data/w07.bin`, `files/data/capsule.bin`,
  `files/data/mdpresult.bin`, `files/data/mdparty.bin`, `files/data/*mot.bin`, `files/dll/w07dll.rel`,
  `files/dll/mdpresultdll.rel`, `files/mess/messdata*.bin`.
- Tell the user to make a **fresh Dolphin save state** after booting the new ISO: a save state holds the old
  code in RAM (this cost a test round in the third session).

| Piece | Source | Status |
|---|---|---|
| Board 11 slot: clone of Snowflake Lake, overlay 0x70, board-number aliases | step `clone_board` | confirmed |
| Music, logo, name card, welcome text | step `pagoda_peak` | confirmed |
| Launch board 11 from Snowflake Lake's icon | aid `clone_board_menu` | confirmed; replaced by 2d, aid deleted 2026-11-26 |
| 2d: board select page 2 (Pagoda Peak's icon, banner, description, half-disc; empty slots locked) | steps `party_pages`, `clone_board`, `pagoda_board` | confirmed (2026-11-26, after three fixes) |
| MP7 map and spaces (with MP7's flags) | step `pagoda_board` (`tools/pagoda/spaces.py`); the retired aids `mp7_map_test`, `mp7_spaces_test` are kept in `plans/pagoda-peak/retired/` | confirmed (2026-11-25, from `w07.bin`) |
| 2a: own archive `w07.bin` (dir 261), data dir table in DOL section 19, `w04*.bin` vanilla again | step `pagoda_board` | confirmed (2026-11-25); Snowflake Lake itself not yet replayed |
| 2b: Pagoda Peak's text (MP7 bank 0x14) as its own bank 0x4B | step `pagoda_board`, `tools/pagoda/mp7_text.py` | confirmed (2026-11-25, a sample of lines) |
| 2c: own orb list (Snowflake's minus Snack, plus the Cannon) and results label "Pagoda Peak" | step `pagoda_board`, `tools/pagoda/label.py` | built 2026-11-25; the shop works (the Cannon is bought there), Snack and label not explicitly confirmed |
| 2c-bis: Cannon orb in the shop (orb id 8, 10 coins, MP7's icon, name, description) | step `pagoda_board` | confirmed (2026-11-25) |
| 2c-bis: Cannon landing rule (11-15 spaces forward, stops before the summit), shot before the roll, landing event | `cannon.c` | confirmed (2026-11-25) |
| 2c-bis: MP7's cannon (climb in, aim, recoil, shot off screen, drop onto the landing) | `cannon.c`, `w07.bin` 44-46 | confirmed (2026-11-25) |
| 2c-bis: odds 15 (about 13%), one-line log, MP7's explosion gag on space 43 | step `pagoda_board`, `cannon.c` `Explode` | built 2026-11-25 (fourth session), not yet tested |
| 2c-bis: CPUs use the Cannon | step `pagoda_board` (CPU orb table row, switch stub), `cannon.c` `PagodaCannonComChance` | built 2026-11-25, not explicitly confirmed |
| Board skeleton, "?" dispatcher, archive closing (`PagodaDirClose`) | `board.c` | confirmed (loads, plays) |
| Star sale at the summit: Master Koopa, house, price sign, price 10→40 | `star.c` | confirmed (2026-11-25) |
| Move carries on from the start after the summit (1a) | `star.c` `MoveEnd` | confirmed (2026-11-25) |
| Cloud flight back down (MP7 `0x115A8`) | `star.c` `ReturnToStart` | confirmed (2026-11-25) |
| Gong of Fate (spaces 19, 38) | `gong.c` | confirmed (2026-11-25), no sinking |
| Bottle rocket (space 23) | `rocket.c` | confirmed |
| Kung Fu Falls (space 65) | `kungfu.c` | confirmed (2026-11-25), including the Star prize |
| Blazing Rock (space 41): 80 + rand(10) presses, Star lost on failure | `blaze.c` | confirmed (2026-11-25) |
| The dragon (space 44) | `dragon.c` | confirmed (2026-11-25) |
| Bowser Time every 3 turns (turns 4, 7, 10 …), 50/50 bridge or stomp | `bowser.c` | confirmed (2026-11-25) |
| Bridge event: 3 bridges, a broken one blocks for a turn, repaired next turn | `bowser.c` | confirmed up to the break; **a player reaching a broken bridge isn't tested yet** |
| Stomp event: stomps 71 and the start, quake knocks everyone a ledge down (masu layer 1, file 1) | `bowser.c` | confirmed (2026-11-25) |
| Bamboo leap (82 → 83) and branch swing (86 → 75) | `gaps.c` | confirmed (2026-11-25) |
| Polish (2026-11-26): view board (X) bounded by MP7's area mesh (`w07.bin` 47 = MP7 `w02.bin` 4), R "Star Space" goes to the summit, MP7's map (Y) and opening cameras | `board.c`, step `pagoda_board` | built 2026-11-26, not yet tested |
| Polish (2026-11-26): roll counter hidden during the Star sale and the cloud ride (`mbMoveNumDispSet`, as Snowflake Lake) | `star.c` `MoveEnd` | built 2026-11-26, not yet tested |
| Polish (2026-11-26): "hear about this board?" -> MP7's explanation (records 43-47, Koopa on the summit, sign 10->40; MP7 `.text 0x9FC`) | `star.c` `PagodaOpeningInst` | built 2026-11-26, not yet tested |
| MP7 tools: `tools/lib/mp7.py`, `tools/scripts/mp7_rel_dis.py`, `mp7_rel_coverage.py` | | done |

**`w07.bin`, 48 files** (`FILES` in `apply_pagoda_board_patch.py` is the one list; `pagoda.h` `FILE_*` must
match it, `tests/test_pagoda_files.py` checks): 0 spaces, 1 masu layer 1, 2 map, 3–5 Snowflake Lake's
shopkeeper / stand / smoke (vanilla `w04.bin` 5, 6, 8, the day versions), 6–11 Master Koopa + motions,
12 house, 13 sign, 14 gong, 15 rocket, 16 Kung Fu rock, 17 cloud, 18–25 Blazing Rock, 26–28 dragon,
29–38 Bowser + motions, 39–41 bridge (intact, breaking, broken), 42 bamboo, 43 branch, 44–46 the Cannon's body,
barrel and explosion (MP7 `capsule.bin` 0x51, 0x50, 0x42), 47 the view-board area mesh (MP7 `w02.bin` 4). From MP7 `w02.bin` except Bowser (MP7
`capsulechar1.bin`), the Cannon (MP7 `capsule.bin`) and the shop. 839 KB. The 11 `<char>mot.bin` have MP7's
fan/chest motions as 126–129 (added by `pagoda_board`).

**What `pagoda_board` owns** (its docstring has every address): DOL section 19 in text slot 3
(`0x802FA1A0`–`0x802FB1A0`: the data dir table with `data/w07.bin`, the moved orb list table, the results label
stub, the Cannon's hook words `0x802FAAA0`/`A4`/`A8` and stubs, the moved CPU orb table; free from `0x802FAFA0`,
map in `docs/patching-guide.md` §4.2); `w07.bin`; message bank 0x4B (MP7's 57 Pagoda records, then the Cannon's
name 57 and description 58); `capsule.bin` entries 87 (orb list) and 88 (Cannon icon); `mdpresult.bin` files
89–93 (bank 6 = the label); a hook in `mdpresultdll.rel` (found by pattern: `random_bonus` moves it); orb rows
8 in `0x80266BDC` and `0x80268500`; the CPU switch entry 8.

**Deployed now (end of the third session):** everything above is in `root/` (Start.dol, `w07.bin`,
`capsule.bin`, `mdpresult.bin`, `mdpresultdll.rel`, `w07dll.rel`, the messages, vanilla `w04*.bin`) and
`src/build/GP6P01-mod.iso` is built from it. `src/build/Start.dol.before_pagoda_board` is the DOL from before
2a. Backups of the originals: `backups/*.bak_before_*` (never overwrite them).

## Key facts (don't re-derive)
- **Learned in the third session (2026-11-25):**
  - **Dolphin save states hold the game's code in RAM:** after a new build, boot it and make a fresh state.
  - **Moving a DOL table:** grep for the label **and** for base + offset readers (data.c reached the data dir
    table as `0x8021AD88 + 0x1168` in 7 places; missing them panicked at boot, `dvd.c:205`).
  - **Orb system:** orb data `0x80266BDC` (10 words: model, frame, description, name, type, colour, price,
    grade << 24, debug name, flags); event table `0x80268500` (7 words: exec, kill, sync, display mode, ...); the
    exec runs as a process with its work at +0x12C (player +0, orb +8). A self orb that moves the player must do
    MP6's order: `mbCapEffUseCreate`, sleep, the orb-use bonus coins (`fn_801D527C`, named
    `mbev_CapRandomBonusCoin`), wait for `mbCapEffUseModeGet < 0`; without the bonus step the effect lasts until
    the dice roll. Turn the player-collision snap off around a move (`mbPlayerColSnapPlayerSet`), or the model
    stays on its space. Running a space's event outside a move: turn phase `GwSystem+0x36` = 7, then
    `mbev_MasuStop(player, masu)` (as `PlayerTurn` at `0x80153E44`).
  - **Orb list rows** (16 bytes): id, 3 prices, 12 signed weights = 4 ranks x {orb spaces 1st half, 2nd half,
    shop}; a weight of 0 = never. **CPU orb table** `0x8026753C` (moved): id + 11 characters x {chance, code};
    no row = the CPU never uses the orb. Shop CPUs pick at random among what's offered.
  - **Space counting:** `mbMasuDispCheck` counts colours 1-6 in party mode (`0x80265408`); colour 0 (path nodes,
    bridges, gaps, the summit) and 7-10 don't count. Space 43 (blue) is the last counted space before the summit.
- **MP7 sources:** the disc is `src/orig/GP7P01.iso`, read with `tools/lib/mp7.py`
  (`read("files/...")`); gclib and capstone are installed in the main Python (both are in
  `requirements.txt`). MP7 `w02.bin` is Pagoda Peak's data
  and `w02dll.rel` its code. The MP7 decomp is US-only and has no board code (and no `gamework.h`
  where expected).
- **Text:** MP7 bank 0x14 is Pagoda Peak's (bank 0x13 is Grand Canal's). MP7 record n is MP6 message
  `PAGODA_MES(n)` = `0x320000 + 26 + n` (`pagoda.h`). MP6 bank 0x32's Chain Chomp ("Wooooof!") is
  Snowflake Lake's own event. Pagoda Peak's rules (records 43–46): Master Koopa sells the Star at the
  top for 10 coins, +10 per purchase, up to 40, then the player goes back to the start.
- **MP7 code by event** (`w02dll` .text offsets; MP7 builds message ids with
  `lis r4,0x14; addi r4,r4,n`):
  - Star sale `0x100C4` (records 7–13).
  - Return trip `0x115A8`: flies along a spline with `w02.bin` model `0x26` to the start, found with
    `mbMasuFind_AttrIdGet(-1, 0x8000)`.
  - Bottle rocket: event `0x2450`, rocket choice `0x284C`, launch `0x2D7C` (records 1–6; record 0 isn't
    used by the "?" event). Stand = the space's type-0x2000 link (81); two rockets (`0x0B`); 75% success;
    landing = flag index 1/2 under `0x60000000` (spaces 76/27). The launch swaps in `0x0C` and flies a
    path with particles (`0x206C` sets up `0x0C`, `0x27` and four more); not ported.
  - Kung Fu Falls (records 14–17, 53): setup `0x569C`, event `0x59A8`, player `0x7180`, CPU AI `0x77E8`,
    catch `0x7E10`, rocks `0x7F8C`, pattern `0x8174`, motion `0x862C`, Star `0x6AA8`. Ledges = space
    65's side node 66 and its link 67; objects follow the 20-point path at .data `0x0` in 4 lanes 300
    wide; clock −1.6 + 0.0044/frame, visible for start+clock in [0, 0.6); 500 frames; jump = 30-frame
    arc to the other ledge (peak 200); catch radius 120 at +60; all coins caught = Star (party mode).
    Full details in `kungfu.c`'s header.
  - Gong of Fate: `0x9B00`–`0xA1D0` (18–23).
  - Blazing Rock (records 24–31): setup `0xA54C`, event `0xA9BC`, prize `0xBDA0`, chest `0xC444`, flame
    particles `0xCA34`. Models `0x15` (burning rock) / `0x17` (out) / `0x18` (flame emitter) / `0x16` (fan)
    / `0x19` (chest) / `0x1A` (T-shirt); sprites `0x2E` (flame), `0x30` (smoke) are MP6-compatible ANM.
    60+rand(10) presses in 10 s; CPU press chance 0.12/0.15/0.17/0.19; prize Star 10% / 5–20 coins 70% /
    T-shirt. MP7's particles use its own particle record layout and sprites from MP7's shared data, so
    `blaze.c` rebuilds the flames on MP6's `Hu3DParticle`. MP6 characters have the same `itemhook-r`
    joint; MP7 player motions are in MP7 `<char>.bin` (dir 0xB6), MP6's in `<char>mot.bin`
    (`CharMotionCreate` only remaps the mot dir). `Hu3DData` is `lbl_802DDAA8` in PAL (not `lbl_802DD9C0`,
    a flag: using it gave invalid reads at board load). The PAL `HU3D_MODEL` doesn't match the decomp's
    `hu3d.h` (hsf at +0xC4, hookData at +0x120, 0x134 bytes), so `pagoda.h` reads models through raw
    offsets (`PagodaModelHsf`, `PagodaModelParticle`); `HU3D_PARTICLE` and its data do match.
  - The dragon, space 44 (no text): setup `0xDCF8`, event `0xE1B8`, throw `0xE7E0`, landing `0xEB5C`.
    Model `0x1B` (joints `h_fire`, `h_dragon`), fireball shape `0x1C`, sprite `0x33`. It lifts the player
    and the space for 60 frames, breathes, chars them (`mbObjBiriQ*`, same in MP6) and flings them
    back to the start space.
  - Bowser Time and the bridge: `0x15454`–`0x16670` (32–38).
  - Records 39–56: "first to the top" mode text and rules (`0xA24`–`0xDCC`); check whether party mode
    uses them.
  - **"?" dispatcher** `0xF5C` (registered at `0x55C`) on `mbMasuMAttrGet(masu)`: `0x80000000` bottle
    rocket `0x2450` (space 23); `0x10000000` Kung Fu Falls `0x59A8` (65); `0x60000` Gong of Fate `0x9708`
    (19, 38); `0x4000000` Blazing Rock `0xA9BC` (41); `0x2000000` `0xE1B8`, not identified (44). It
    returns 1 when nothing ran, the same as MP6's `ev_MasuHatena` (`0x80176EA0`) expects.
  - Gongs: file `0x13` hooked on the map's `h_dora0`/`h_dora1`, with the price sign on each gong's
    `h_rate1` (one model, drawn at every joint that hooks it). MP7's "`mbObjScaleSetV`" match
    (`0x80170F28`) is really a position set: the two compile alike.
  - MP7 player motion numbers differ from MP6's: MP6 1 idle, 4 jump, 5 land, 6 stun, 7 Star get, 11
    dice-block hit (has its own jump in it), 12 (sinks the player outside the DOL's coin events). MP6's
    slot → animation table is `.rodata 0x8021A3E8`.
  - Master Koopa rides a cloud (`w02.bin` `0x26`, scale 0.75, MP7 `.text 0x1498`) whenever he drops in;
    MP7 hides it at the summit.
  - Master Koopa is `w02.bin` file `0x35`, created at `0x6E4` with motion table `0x36`–`0x3A` (.data
    `0x4B4`) and hidden until the sale. File `0x25` (at `0xFF90`) is his house with the summit
    platform (motion paused with `0x40000002` until the sale); file `0x14` (at `0x1A70`) is the price
    sign, hooked on the house's `h_rate0` joint, paused, motion time `{0, 9, 19, 29}[level]`; file `0x26`
    (at `0x14E0`) is the return-trip vehicle. MP7 `0x801714f8` / `0x801715fc` are `mbObjAttrSet` /
    `mbObjAttrReset` (the coverage tool lists them as missing).
  - MP7's sale animation: Koopa at summit + (0, 68, −700), motion 1; the player turns to 180; camera
    `mbCameraMoveMasu(summit, (−20,0,0), (0,200,0), 2200, −1, 30)`; after 30 frames motion 2 while he
    walks to z −400 over 120 frames; motion 3 to talk; motion 4 (once) on a purchase; motion 5 before
    the trip back; hidden after it. Shifts are `(0, 4.0, 0x40000001)`.
- **MP7 space flags** (dropped by `mp7_spaces_test`; the C board can use them the way MP7 does):
  - each colour-3 "?" space has its own bit: 19 `0x20000`, 23 `0x80000000`, 38 `0x40000`,
    41 `0x4000000`, 44 `0x2000000`, 65 `0x10000000`;
  - index pairs, probably the bridge or gates: 24/25 `0x400000`/`0x200000`, 29/30
    `0x600000`/`0x800000`, 33/34 `0xA00000`/`0xC00000`;
  - summit 54 `0x10000`; others at 27, 71, 75, 76, 82, 86.
- **File 0 vs 2, settled:** MP7 `w02dll` .text `0x124`–`0x194` tests GwSystem byte 0 bit 7 (`partyF`,
  the same bit in MP6): party mode loads file 0 and reads file 1 as masu layer 1 (`mbMasuDataRead`);
  otherwise files 2 and 3. Layer 1 isn't loaded yet (probably the trip down or Bowser Time).
- **MP6 engine facts:**
  - **`mbSinRad`/`mbCosRad` take radians** (a 2048-entry table indexed by angle × 8192/2π, `lbl_802E0974`).
    MP7's matching functions take degrees, so MP7 angles go through `PagodaSin`/`PagodaCos` (`pagoda.h`).
    Passing degrees caused Master Koopa's jittery drop-in and the Kung Fu Falls hit wobble.
  - **Close the board archive after every model made mid-game** (`PagodaDirClose`). Reading one file loads
    the whole archive into the DVD heap until `HuDataDirClose`; the old `w04*.bin` was about 1.5 MB with every event's
    models, and leaving it open crashed Kung Fu Falls' Star prize (`OSPanic dvd.c:63`, allocation failure).
    MP7 closes `0xFE0000` after its events the same way. Close `<char>mot.bin` after extra player motions
    with `CharMotionDataClose`.
  - The move-end hook (`mbev_MasuMoveEndSet`) gets `(player, masuId)`. Returning 0 counts the step;
    non-zero doesn't, and the move stops once `GwPlayer.moveNum` (+0x0A) is 0 (`PlayerMove`,
    `0x80154B78`).
  - All hooks are NULL-checked, and `mbMasuInit` clears the masu hooks.
  - `mbev_MasuHatenaSet` = "?" spaces; `mbev_NextTimeSet` = day/night switch.
  - Shops: `mbev_ShopExInit` (colour-9 spaces with type-0x20 nodes).
  - Every MP6 board sells its Star in its own code.
  - `GwSystem.boardWork` is the board's saved state. Word 0: bits 0–1 the Star price level (`star.c`),
    bits 2–4 the broken bridges, bits 8–15 the last turn Bowser Time's hook handled (`bowser.c`).
- **Tools and gotchas:**
  - `build/GP6P01/include/p01_names.h` has real names for nearly every board function: grep it
    before guessing.
  - `mp7_rel_coverage.match()` maps MP7 calls to MP6 functions.
  - capstone stops at Gekko paired-single words, so disassemble MP7 code word by word.
  - mwcc runs with `-nosyspath`, so the REL source folder is passed with `-i`.
  - **`python -m tools.scripts.mp7_rel_dis w02dll 0x100c4`** lists the MP7 function containing that
    .text offset, with each call shown as its MP6 match and name (it takes about 14 s to match). Give
    two offsets for a range. `--high 0x14` lists where message ids `0x14nnnn` are built; `--high 0xfe`
    lists `w02.bin` data numbers. MP6 board RELs are already disassembled with names in
    `build/GP6P01/<rel>/asm/`, and `p01_names.h` maps their `fn_` names.

## Next steps (in order)

### 1. The one open check: a player reaching a broken bridge

The user confirmed everything else in Dolphin (2026-11-25): the cloud flight and the move carrying on,
the Star price, the gong, Kung Fu Falls' Star prize, Blazing Rock, the dragon, the bridges drawn and
broken, the stomp, the bamboo and the branch. Still to test (the user will do it later): when a player
steps onto a broken bridge's first space (25, 29 or 33) they should see record 35, hop back to the space
they came from and end their move there; the bridge is repaired at the start of the next turn (record
36). If it goes wrong, look at `bowser.c` `PagodaBridgeBlocked` (called first from `star.c` `MoveEnd`)
and `BridgesRepair`. To reach Bowser Time sooner, build with `BOWSER_TIME_EVERY` 1 in `bowser.c` (every
turn from turn 2), then set it back to 3.

Ship any fix through `pagoda_board` (see "Where things stand"), and record only what the user confirms.

### 2. A real board slot (the big one)

Today board 11 borrows Snowflake Lake's files and slots, and is started from Snowflake Lake's icon by a
test aid. The goal is a board that stands on its own and is built by `STEPS`, not test aids. Read
`docs/board-tables.md` first: it maps every table that hard-codes the board set. `tools/lib/board_tables.py`
is the machine-readable version and `python -m tools.scripts.board_tables_dump` checks the tables against
vanilla.

Do the sub-steps in this order. Each one ends with the user testing in Dolphin before the next starts,
so a crash can be traced to one change.

**2a. Its own archive (`w07.bin`), and Snowflake Lake's archives back to vanilla: confirmed in Dolphin
(2026-11-25)** after the boot-panic fix below: the game boots and Pagoda Peak plays as before. Not yet
replayed: Snowflake Lake itself (needs `clone_board_menu --off`). Decisions taken with the user: a real step now
(`pagoda_board`, last in `STEPS`) rather than more test-aid work; one archive for day and night, with MP6's
day/night cycle still running; the aids `mp7_map_test` and `mp7_spaces_test` retired (copies in
`plans/pagoda-peak/retired/`), their space-table code moved to `tools/pagoda/spaces.py`.
- **DOL:** section 19 in text slot 3 (`0x802FA1A0`–`0x802FB1A0`, arena clamp raised): the path
  `data/w07.bin`, then the data dir table copied with dir 261 appended (`0x802FA1C0`–`0x802FA9F8`); its 3
  label references (`0x80007688`, `0x800084A4`, `0x80008BC4`) re-pointed, plus 7 reads through a base
  register (`0x8021AD88` + `0x1168`) rewritten in place. **First Dolphin test (2026-11-25): boot panic
  `dvd.c:205` File Open Error**, because those 7 reads still used the old table (no entry numbers);
  fixed the same day and confirmed. `HuDataInit` counts the table
  (`DataDirMax`) and writes each file's disc entry into it, so nothing else is sized to 261.
- **Day/night, settled:** `mbObjDirSet` (`fn_80168E9C`) only stores the two dirs; the readers
  (`fn_80168258` and 5 copies) swap a data number's dir only when it equals the other time's dir. With
  `mbObjDirSet(DIR_BOARD, DIR_BOARD)` the swap is a no-op. The shopkeeper's day and night models differ
  (`w04.bin` vs `w04n.bin` 5 and 6); `w07.bin` has the day ones, so the shop looks the same at night.
- **Engine loads from the board dir:** none by a fixed number. The shop (`mbev_ShopExInit` →
  `fn_801E9428`) creates only the model passed in, with no motions; `mbCapThrowColCreate(-1)` loads
  nothing.
- **REL:** `pagoda.h` `DIR_BOARD 0x01050000`, `FILE_*` renumbered; the Koopa and Bowser motion tables are
  built from `FILE_KOOPA + n` / `FILE_BOWSER + n` (one table each, no night copy). No dir 233/234 is left in
  the REL (checked: 12 `lis 0x105`, 14 data words).
- **Checked:** pytest and ruff pass; both scripts are idempotent (identical hashes on a second run); the
  build diff against a snapshot changes only `main.dol`, `w07.bin` (new), `w07dll.rel` and `w04*.bin`
  (back to vanilla). Not done: the `--only` test from a fresh build (it would rebuild everything).
- **To check in Dolphin:** the game boots (a missing `w07.bin` would `OSPanic` in `HuDataInit`); Pagoda
  Peak loads and plays as before (map, spaces, Star sale, every event, Bowser Time, the leaps); the
  shop; a day/night switch (nothing should vanish or reload); **Snowflake Lake plays normally** (vanilla
  archives, through its own icon once `clone_board_menu` is off, or a normal build).

**2b. Its own message bank: confirmed in Dolphin (2026-11-25)** (the user checked a sample of the lines;
all fine).
- `pagoda_board` adds **bank 0x4B** after the 75 vanilla banks with the new `tools.lib.messages.set_bank`
  (unit-tested): MP7 bank 0x14's 57 records, so `PAGODA_MES(n)` = `0x4B0000 + n` (MP7 record n). It also
  strips the records `pagoda_stub` used to append to bank 0x32, which is vanilla again (checked in all six
  languages; every other vanilla bank unchanged; bank 0x4B byte-identical to the old records 26–82).
- `splice_bank` (used by the five `write_bank` steps) now accepts a target with extra trailing banks, so
  re-running an earlier step doesn't fail on the 76-bank file. No other step adds a bank.
- `pagoda_stub` no longer touches the message files. The REL loads ids with `lis 0x4B` (44), none with 0x32.
- **To check in Dolphin:** every Pagoda Peak line still shows the right text (welcome is bank 0x2C, not
  this one; then the Star sale, gong, rocket, Kung Fu Falls, Blazing Rock, Bowser Time); Snowflake Lake's
  own text (the Chain Chomp, bank 0x32) when it is replayed.

**2c. Orb list, results and records: built (2026-11-25); the shop works (the Cannon is bought there); the missing
Snack orb and the results label still to confirm with the user.**
Decided with the user: records keep counting under Snowflake Lake; Pagoda Peak gets its own orb list,
Snowflake Lake's without the Snack orb (and, later, MP7's Cannon orb: 2c-bis); its results show a
"Pagoda Peak" label, two lines like MP6's.
- Orb list: `capsule.bin` entry 87 (`0x140057`): Snowflake Lake's 11 orbs minus Snack (`0x1E`), so
  Mushroom, Super / Sluggish / Metal Mushroom, Warp Pipe, Spiny, Piranha Plant, Podoboo, Tweester,
  Paratroopa (Star Trap is still appended at run time). The orb list table moved to section 19 with
  {11, `0x140057`}; `mbCapListRead`'s board read no longer aliases. `castaway_wheel` now accepts the
  88-entry `capsule.bin` (it drops entry 87; `pagoda_board` re-adds it later in the chain).
- Results: `mdpresultdll`'s tables are the same for boards 0–4, so only the board-name label showed
  "Snowflake Lake". `tools/pagoda/label.py` adds bank 6 to the label sprite (`mdpresult.bin` 89 English,
  90 German, 91 French, 92 Italian, 93 Spanish): MP6's Snowflake pill with the lettering cleared and MP7's
  lettering from `bdresult*.bin` (file 101 English, 100 the others; bank 1), split at the space
  ("Pagoda / Peak", "Pic / Pagode", "Picco / Pagoda", "Pico / Pagoda"; German "Pagodia" one line).
  A stub (`0x802FAA80`) replaces `mr r5,r30` before `HuSprBankSet(group, 1, board)`; that site is found by
  its words because `random_bonus`'s rebuild moves it (vanilla `.text 0x18FB4`, built `0x19118`).
- **To check in Dolphin:** the shop sells no Snack orb on Pagoda Peak (and still does on other boards);
  the results screen after a Pagoda Peak game shows the "Pagoda Peak" label (and other boards' labels are
  unchanged); records still count under Snowflake Lake.

**2c-bis. MP7's Cannon orb: done; the user is happy with it (2026-11-25).** The tidy-ups (odds 15, one-line log, the
explosion gag) were built in the fourth session; sounds wait for polish, CPU use is still to confirm; see "Next
session" at the top. The record below is how it was built. MP7: a
self orb only on Pagoda Peak; a cannon appears, the player climbs in and is fired to a higher level of the
mountain, a random distance; spaces flown don't count for the Running Star; used on the last space, the
cannon fires them straight up and explodes as they fall. The user wants it copied from MP7 as closely as
possible. It is ported to C (Route A, running MP7 code with remapped calls, was ruled out in Experiment 2).

*Research (2026-11-25):*
- **MP7 orb data** `main.dol 0x80296F8C`, 10 words per orb as in MP6 (`0x80266BDC`): the Cannon is **MP7 orb id
  5**: model `0x1B0005` (MP7 `capsule.bin` file 5), frame `0x1B0022`, description `0x1B0005`, name
  `0x1B0047` (MP7 message bank 0x1B records 5 and 71), type 0 (self), price 20. The code reads it through
  base `0x80296F88` (stride 0x28; type at +0x1C).
- **MP7 orb event table** `0x80298348`, 8 words per orb `{exec, kill, 0, 0, a, b, data, 0}` (MP6's
  `0x80268500` has 7: `{exec, kill, 0, 2, 0, -1 or data, 0}`). **Cannon row 5: exec `0x801A8E7C`, kill
  `0x801AAE30` (a `blr`).** The code runs from `0x801A8E7C` to `0x801AC5A8` (about 3500 instructions, 6
  functions: `0x801A8E7C` exec, `0x801A9C48`, `0x801AAE34`, `0x801AB1D8`, `0x801AB638`, `0x801AB7C4`). It loads
  MP7 `capsule.bin` files `0x50`, `0x51` (cannon models) and `0x42` (effect), all HSFV037, and MP7
  `mariomot` file 8 (a player motion; check whether MP6's matches), and plays sound `0x443` among others. No
  text. MP6 matches for its calls: most engine calls are exact (process, camera, masu, sound, PSVEC, the
  `mbev_Cap*` helpers); about 25 MP7 functions match badly and need identifying by hand, mainly
  `0x8016B374`-`0x8016B928` (player/object accessors, wrongly matched to `mbMasuChanceKill`), `0x8016894C`,
  `0x80168A04`/`0x80168A30`, `0x8016D080`, `0x8016B610`/`0x8016B760`/`0x8016B804` (object creation),
  `0x801610F8`, `0x80161204`, `0x801A49EC`, `0x801A4C64`, `0x801FA300`/`0x801FA39C`, `0x80204DD4`,
  `0x80203410`. The `0x800F96xx` "missing" ones are `_savegpr`/`_restgpr`.
- **MP7 CPU logic:** MP7's orb-choice switch (`0x801EFF9C`, table `0x80297EA0`) asks a board hook for orbs
  5-7 (the board-only orbs): `w02dll .text 0x1334`, registered with MP6's `mbCapThrowHookSet`
  (`fn_801C4144`, same setter in both games). For the Cannon (bit 0) it says yes when a board state byte
  (`w02dll` .data/.bss `+0x8B0`, bits 3-4) is below 2; bit 1 = within 10 steps of the summit (attr
  0x10000), bit 2 = within 15 of the start. MP6's CPU switch is `mbCapComChanceGet` (`fn_801C938C`, `cmplwi
  0x1F` + jump table): a new id in 0-0x1F falls on the EMPTY case, so CPUs never use it until that case is
  added.
- **MP7 shop row** (Pagoda Peak's list, MP7 `capsule.bin` 0x5A): `05 14 14 0a 0a 0a 0a 14 0a 0a 14 1e 1e 14 00
  00` (orb 5, prices 20/20/10, then the weights), same row layout as MP6.
- **MP6 slot:** the free orb ids are `0x08`, `0x09` (in the self-orb range 0-9), `0x12`, `0x13`, `0x1A`-`0x1D`.
  Use **id 8**.

*Stages (each tested in Dolphin before the next):*
1. **The orb exists and can be bought and used (placeholder effect): confirmed in Dolphin (2026-11-25):** the
   orb shows MP7's cannon icon in the green frame with its name and description, and using it logged
   "Cannon orb used by player 2".
   Built as below, except: price **10** in the orb row and all three shop prices (the user's choice; MP7 20),
   grade 'C' (`0x43`); the event row points at two **DOL stubs** in section 19 (exec `0x802FAAC0`, kill
   `0x802FAAE0`) that jump through hook words `0x802FAAA0`/`0x802FAAA4`, which `cannon.c` sets at board init
   and clears at kill and in `_epilog` (no hook: the exec stub ends the orb's process), instead of the REL
   writing the row itself. The name uses MP6's orb-name header `00 07 00 01`; the description converts as
   is. The placeholder exec: `mbev_CapWait`, `mbCapEffUseCreate`, wait for `mbCapEffUseModeGet == -1`,
   `OSReport` ("Cannon orb used by player n"), `HuPrcEnd`.
   **Odds:** MP7's shop row was copied first, but MP6 reads the 12 weights differently (orb spaces 1st half =
   columns 0-3 by rank, 2nd half = 4-7, shop = 8-11; see `docs/board-tables.md`), so 3rd and 4th place got 0%
   in the shop and the user couldn't find it. For testing (the user's choice) it now weighs 120 in all 12
   columns: about 50% per pick everywhere. Tune it (`CANNON_WEIGHTS`) after stage 2.
   **To check in Dolphin:** Pagoda Peak's shop offers "Cannon" for 10 coins with its model and description;
   buying and using it plays the use effect, logs the line (View > Show Log) and the turn goes on.
   Original plan for stage 1: `pagoda_board` fills MP6 orb row 8
   (`0x80266BDC`: model = MP7 `capsule.bin` 5 appended to MP6 `capsule.bin` as entry 88, frame `0x14001C`
   (self, green), name/description = MP7 bank 0x1B records 71/5 as bank 0x4B records 57/58, type 0, price 20,
   flags as the other self orbs) and adds the MP7 shop row to Pagoda Peak's list. The event row 8
   (`0x80268500`) points at the board REL: `board.c` writes its exec/kill into the row at init and puts the
   vanilla words back at kill (the orb only exists on Pagoda Peak's list). The first exec just logs and
   returns. Check: the shop offers it, the orb shows its model, name and description, and using it doesn't
   crash.
2. **Port MP7's exec** (`cannon.c`): identify the badly matched MP7 functions first (disassemble each, as for the
   earlier events), then port the 6 functions with the cannon models (`w07.bin`) and motion. **Keep MP7's look
   (the cannon appears, the player climbs in, is fired and lands) but use a simpler landing rule (the user's
   choice, 2026-11-25):**
   - MP7's rule, for the record (`0x801AAE34` + walk helper `0x801AB1D8`): roll 11 + rand(5) steps; mark the blue/red
     spaces 10..n steps ahead on every forward branch; keep those within +-45 degrees of world +Z and within
     3000 + 50 x turn (max 6000) horizontally; pick one at random (all candidates if none pass; if none at all,
     retry from 1 step; still none = the last-space gag). On Pagoda Peak "up the mountain" is -Z (start z 4944,
     summit z -4591), so the +Z cone looks odd; not ported.
   - **Pagoda rule:** roll 11-15 steps; walk forward counting only spaces that count as a step
     (`mbMasuDispCheck`), taking the branch with fewer steps to the summit at a fork; land on whatever space type
     it reaches (any colour or event). Never land on a broken bridge's space (`bowser.c`): land on the space
     before. Flown spaces don't count for the Running Star (the player is placed, not walked).
   - **Near the Star:** the summit (space 54, flag 0x10000) is never passed or landed on: if it is within range,
     land on the last space before it, so the player still walks onto it with the dice and gets the Star offer.
     If they already stand on the space right before the summit (nowhere to go), play MP7's gag: fired straight
     up, the cannon explodes, they land back where they were.
   - **Part 1 (landing rule + flight; confirmed after the two fixes below):** `cannon.c` `PagodaCannonTarget`
     and `Fly` (camera follows the player, a crouch with rumble, an arc 1500 + 0.15 x distance high over 90 frames,
     a landing shake; nowhere to go = straight up 2500 and back down); `bowser.c` `PagodaBridgeBroken`. No sound
     yet (MP7's ids differ). Simulated on Pagoda Peak's table: shots land 11-15 counted spaces up the trail
     (e.g. 27 -> 19/20/31/12/8); space 43 is the last counted space before the summit, so shots near the top
     stop there and a shot from 43 goes straight up. Bridge and gap spaces are colour 0 (not counted), so they're
     flown over. Dolphin's log shows "Cannon orb, player n from space a to b".
     **To check:** the flight and landing, the dice roll afterwards from the new space, a shot near the top
     (stops on 43), the summit still reached by walking.
     **First test (2026-11-25):** the landing works ("player 2 from space 6 to 39"), but the shot only happened
     after the dice roll, the landing space (a Duel space) didn't trigger, and there was no cannon. Fixes (built,
     not yet tested): fly right after `mbCapEffUseCreate` and wait for `mbCapEffUseModeGet < 0` only at the end
     (that state lasts until the dice roll; MP6's Bullet Bill orb does the same); the shot is now straight up off
     screen, a fade, the camera on the landing space, a drop onto it; then the space's event runs as
     `PlayerTurn` runs it after a move (turn phase byte `GwSystem+0x36` = 7, `mbev_MasuStop`, camera back,
     `mbPlayerRotateStart(p, 0, 15)`, `mbPlayerMotIdleSet`). Not triggered: orbs placed on the landing space
     (`mbev_MasuCapStop`, whose "turn ends" path loops inside `PlayerTurn`). **To check:** the order (orb,
     shot, landing event, then the dice); events that start a minigame (Duel, Bowser, DK) mid-turn, which may
     resume the turn oddly; the gag from space 43 (no event).
     **Second test (2026-11-25, logs):** the walk is right (space 6 -> 38 on a roll of 13, -> 1 on 12), but on a
     plain landing the model stayed on space 6 (the gong landing only looked right because the gong event moves the
     player itself). Fix, copying MP6's own movement orbs (Warp Pipe `mbev_CapDokan` `fn_8019C620`, Bullet Bill):
     use effect, rumble, sleep, the orb-use bonus coins (`fn_801D527C`, named `mbev_CapRandomBonusCoin`; without
     it the use effect lasts until the dice roll), wait for `mbCapEffUseModeGet < 0`, then
     `mbPlayerColSnapPlayerSet(p, 0)` around the move (the collision snap held the model on its space) and
     `(p, 1)` after the landing. `cannon.c` logs each walk step by step while testing.
     **Confirmed in Dolphin (2026-11-25):** the shot before the roll, the landing and its event.
   - **Part 2 (MP7's cannon): confirmed in Dolphin (2026-11-25), "working well".** MP7's exec read in full (`0x801A8E7C`-`0x801A9C48`):
     body = MP7 `capsule.bin` 0x51 (`cannon01`), barrel = 0x50 (`cannon00`, hooked on the body's `center`),
     explosion = 0x42, now `w07.bin` files 44-46 (`FILE_CANNON*`); MP7 `mariomot` 8 = MP6 `mariomot` 8 byte for
     byte. Ported: the cannon on the space facing 180 at scale 0; the player hops 300 (30 frames), drops in with
     mariomot 8 shrinking to 0.5 while the cannon pops up (`t + 0.5 sin 180t`); player hidden; body swivels +-45
     (90 frames) and turns to the heading (2.5 deg/frame); barrel nods (`rotX -45 sin 180t`, 120 frames, via
     `mtxRot` + `mbObjMtxSet`) and tilts to `-90 - elevation` (1.5 deg/frame); 12 frames, recoil (body motion),
     9 frames, the player out of the barrel and off screen (40 frames) while the cannon shrinks (12 frames). MP7's
     own sounds (`0x443` into the cannon, `0x444` fire, `0x448`, `0x323` explosion) and flight (`0x801AB638`) not
     used. **To check:** the cannon's size and facing (MP7 faces it 180 + heading), the barrel's nod and tilt
     direction (rotX sign), the player's hop and shrink, the recoil.
3. **CPU use: built 2026-11-25, not explicitly confirmed (ask; "Next session" item 1).** `mbCapComChanceGet` (used by `mbCapSelectComGet` to pick the orb to
   use and `mbCapSelectDeleteComGet` to pick one to throw away) returned -1 for orb 8: no row in the CPU orb table
   (`0x8026753C`, rows of 0x2E: id + 11 characters x {s16 chance, u8 code, pad}). `pagoda_board` moves the table to
   section 19 (`0x802FAB00`, reference `0x801C93AC`) with a row for orb 8 = MP7's own CPU row for the Cannon
   (MP7 `0x80296940`, stride 0x32, row 5, first 11 characters: 30 30 10 50 10 30 10 10 50 10 50), and points the
   orb-id switch's entry 8 (jump table `0x802680B0`) at a stub (`0x802FAF60`) calling `PagodaCannonComChance`
   through hook word `0x802FAAA8`: 0 when a shot can't move the player (space 43), at least 50 when a full 15-space
   shot fits before the summit, else the table's chance; throwing away is `100 - chance`, so a useless Cannon goes
   first. Buying: the shop's CPU choice is random among the orbs offered (`ev_Shop` `mbRandMod`), so CPUs already
   buy it. **To check:** a CPU using the Cannon (log line), and not on space 43.

Old notes for 2c: Board 11 still aliases to board 3 for the orb list
(`0x80267D20`, searched, needs a `{11, capsule file}` row), `mdpartydll`, `mdpresultdll` and the save
records (`docs/board-tables.md`, "Save data": don't change the save format; keep counting under another
board or skip the two record calls). Decide with the user whether results under Snowflake Lake are
acceptable. If not, give board 11 its own orb list row (moved table in section 18) and results
entries (`mdpresultdll` `result_counts` +0x3A8, `result_sprites` +0x3B4).

**2d. A 7th icon in `mdpartydll` (the next big job).** Today board 11 is reached only through the test aid
`clone_board_menu`, which points Snowflake Lake's icon (cursor position 3) at overlay 0x70. The goal: a 7th board
on the party board select with Pagoda Peak's picture, name and description, Snowflake Lake back on its own icon,
and the aid retired. `clone_board` owns `mdpartydll.rel` (rebuilt from the original on every run, its 7 board
reads hooked with `add_calls`), so 2d's changes go there or in `pagoda_board` after it.

**Research done (fourth session, 2026-11-25): the full map is in `docs/board-tables.md` "Party menu and
results"**: every per-board slot on the screen (icon model copies, texture and sprite animations, banners) is
full, the description slot (bank 2 record 15) is free, MP7 has no usable board-select art. **Decided with the user
(2026-11-25):** a **second page** of boards (the user plans to add more boards later, so pages of 6 scale:
page 2 = boards 7-12, Pagoda Peak alone for now); Pagoda Peak **unlocked from the start**; its octagon and
half-disc pictures made from **the user's Dolphin screenshot** of the map. Design sketch: reuse the 6 icon
model copies (11-16), the banner sprites and the half-disc object, and swap their texture / sprite animations
to page 2's set when the cursor crosses the page edge (the page-2 animations loaded into a new table, not the
full ones); hide the unused icons on page 2; cursor = page x 6 + slot; wrap over all boards. Next: the build plan. The notes below are the older summary; the doc supersedes them (MP7
`mdparty7.bin` 147-151 turned out to be mode-select art, not boards).

*Known before the research* (`docs/board-tables.md` "Party menu and results", `tools/lib/board_tables.py`):
- `party_board_dlls` (rodata +0x7C): the 6 cursor positions -> overlays 0x7B-0x80, copied to the stack in `fn_1_129C`
  and `fn_1_2DF8C`; the cursor is the halfword at `lbl_1_bss_9F4+4`.
- The select screen is 3D: `fn_1_19510` builds the 6 boards in a `cmpwi 6` loop, 4 parts each; the icon layout is in
  `lbl_1_data_8A4` (x = -200, -120, -40, 40, 120, 200); per-board flags in `lbl_1_data_C66` (7) and `lbl_1_data_E5E`
  (6); `fn_1_305E0` writes `GwCommon.lastBoard` and resets the cursor from `boardNo` after a game.
- The user's screenshot of the screen: the 6 boards are octagon pictures in two staggered rows under a name banner
  ("Towering Treetop"), with a one-line description in the window below ("New to the game? This treetop romp is
  perfect for first-time players!"), arrows left and right.
- Unlocking: `GwCommon.map7Unlock` (+0x428 bit 6) is written at start-up and never read: a free save bit, if the
  user wants Pagoda Peak locked at first (ask).
- MP7 assets that may fit: `mdparty7.bin` files 147-151 (one per language) are 6-bank sprites with a 256x160 picture,
  256x64 banners and 96x88 images per MP7 board (bank 1 = Pagoda Peak); `bdresult*.bin` has the board names (used by
  2c's label); `tools/pagoda/label.py` shows how to read MP7 sprites and rebuild MP6 ones with an extra bank.

*Research checklist (read-only, write the answers into `docs/board-tables.md`):*
1. What each board's octagon is: a model or a sprite, which file of `mdparty.bin` (or another archive) per board,
   and how `fn_1_19510`'s 4 parts per board are made. Same for the name banner and the description (message ids;
   which bank holds "New to the game? ...").
2. Every place that loops or bounds-checks on 6 boards (`cmpwi 6`, `cmplwi 5`, tables of 6), including the cursor
   movement (left/right wrap), the arrows, the camera, and `fn_1_305E0`.
3. Every read of `party_board_dlls` and of the per-board tables, by label **and** by base + offset (the data dir
   table had 7 hidden base + offset readers that crashed the first build; grep for offsets from nearby labels too).
4. What else the select screen does per board: records shown for the board (the save arrays only have 6 boards;
   records count under Snowflake Lake), music, any `boardNo` use.
Then show the user the options for laying out 7 boards (a 7th octagon squeezed into the two rows, or a page
switch with the arrows) and build the chosen one. Ask whether Pagoda Peak should be unlocked from the start.

**2e. Promote the rest to `STEPS`.** The step `pagoda_board` exists since 2a (DOL table and `w07.bin`).
Fold what `pagoda_stub` still does into it (minus the `--off` path): build and install the REL, the message
bank (after 2b), and the `<char>mot.bin` motions (written to `build/` instead of `root/data`). Then remove
`pagoda_stub` from `TEST_AIDS`, update the dependency table row in `tools/README.md`, test with `--only`
from a fresh build, and check the full chain's diff against a snapshot (only owned files change;
`w03Dll.rel` grows on every run, known). Remove `clone_board_menu` once 2d works.

### 3. Polish (after step 2, any order; ask the user which they want)
- Sounds: MP7's sound ids differ from MP6's. Find MP6 equivalents for the events (Bowser's music was MP7
  track 0x16; landing, rumble, gong, rocket).
- The opening's Star intro (`mbOpeningStarInstHookSet`, still NULL). Done 2026-11-26: the board explanation
  (`mbOpeningInstHookSet`) and MP7's opening/map cameras and view-board area.
- Day/night visuals (`mbev_NextTimeSet`): the user chose to keep MP6's day/night cycle (2026-11-25), on
  one archive. The shopkeeper uses its day models at night too (`w04n.bin` 5/6 differ); a night
  look would need extra files in `w07.bin` and a switch in the REL.
- Bowser Time debris particles (sprite `0xFE0034`), the cloud's trail, the house's particle.
- CPU behaviour: check CPUs at the bridges (MP7 adds the bridge links in path-search mode 3 through
  `mbev_MasuLinkTblHookSet`, `.text 0x1048`) and balance Blazing Rock for easy CPUs (they average about
  60 presses against a target of 80–89, so they nearly always fail and lose a Star).
- Records 39–56 ("first to the top" mode) are unused in party mode; leave them.

**Verify every step:**
- `python -m pytest` (from `src/`) and `ruff check .` (from the repository root).
- Run each patch twice (identical hashes); for aids, check that `--off` restores the bytes.
- For new C, list the REL's module-0 relocations and check each resolves to the intended `p01_names.h`
  name (the snippet used all session: `walk_relocs(rel, import_blocks(rel)[0])` against
  `build/GP6P01/include/p01_names.h`).
- Deploy to `root/`, run `python -m tools.scripts.build_iso`, and let the user test in Dolphin. Nothing
  counts as working until the user confirms it.

## Build record (what was built in the sessions of 2026-11-25, with the reasons)

Kept for its research details; the current status is the table at the top. Step numbers are the old
plan's (1a–1f = the first Dolphin fix list, 6/6b = Bowser Time, 7 = the flight, 7b = the leaps).

0. **Built and deployed (2026-11-25, second session), waiting for the user's Dolphin test:** all of 1a–1f
   below. `root/dll/w07dll.rel` is 66948 bytes and `src/build/GP6P01-mod.iso` is rebuilt. What changed:
   - **1a** (`star.c` `MoveEnd`): the hook no longer zeroes `moveNum`. In `PlayerMove`, the hook runs inside
     `mbev_MasuMasuStart` (`fn_80176C44`). A non-zero return skips `mbev_MasuMove` and the step count, and
     the loop goes on while `moveNum != 0`, starting the next step from `masuId`. So the hook counts the
     summit the way the engine does (`mbMasuDispCheck(54)`, sound `0x3EE`, `moveNum - 1`, `mbMoveNumKill`
     at 0) and returns 1. To check: the dice counter, 1 move left (should stop on the start), and the fork
     after the start.
   - **1b**: `mbev_MasuMasuStart` brackets the move-end hook with `mbPlayerColSnapPlayerSet(p, 0)`/`(p, 1)`,
     but `ev_MasuHatena` only turns it off. The gong now calls `mbev_PlayerColMasuSet(player, masu, 1)`
     after the jump back and at the end. Kung Fu Falls (each jumper, on `GwPlayer.masuId`) and Blazing Rock
     do too at their end. If the gong player still sinks, log Y with `OSReport`.
   - **1c**: Koopa at ledge + (100, 80, 0) (was 150); `CameraOnLedge` centre y + 200 (was 100), zoom 2400
     (was 1600). Also a real bug: the intro hid only Koopa, so **his cloud stayed on screen all game**. The
     new `PagodaKoopaHide()` hides both. Tune with the user.
   - **1d**: the particle TEV for I8 is `RASC` alone (vertex colour; the texture only gives alpha). Flames
     are now r 255 / g 100–159 / b 32, alpha 0xE0, size 130–160 (was 500–600), **normal** blending (was
     additive). Smoke is grey 0x60. Tune with the user (`FLAME_SIZE`, `FLAME_SIZE_RANGE`, the colour in
     `FlamesLight`).
   - **1e**: `StarLose` in `blaze.c` after "Too bad": `mbStarDispPlayerCreate(p, -1)`, wait for
     `mbStarDispCheck`, `mbPlayerStarAdd(p, -1)`, only if `mbPlayerStarGet(p) > 0`. `mbDiceFadeSet` is
     left out: it only fades the dice block (`lbl_802D99E4[p] + 0x4C` bit 0x40), which isn't on screen
     here.
   - **1f**: `PRESS_TARGET` 80 (raised from 70 after the user's test).
   - **Confirmed by the user (2026-11-25):** Blazing Rock plays well, Kung Fu Falls' framing and hits are
     right. After that test the flames were made bigger (220–270, alpha 0xFF, g 120–199).

1. **Fix list from the Dolphin test of 2026-11-25 (built: see step 0).** The board loads
   cleanly since the `Hu3DData` fix (`lbl_802DDAA8`). Confirmed: the dragon (space 44) works, Blazing
   Rock's prizes work, Kung Fu Falls plays (only Master Koopa's framing is wrong). Every fix is in
   `src/src/REL/w07Dll/` and ships through the test aid `pagoda_stub`: rebuild with
   `python -m tools.patches.test_aids.apply_pagoda_stub_patch` (from `src/`), copy
   `build/GP6P01/files/dll/w07dll.rel` to `root/dll/`, then run `python -m tools.scripts.build_iso`.

   **1a. The Star sale ends the move (star.c).** After the summit (bought, declined or too poor) the
   player is warped to the start and the move stops, but the dice display still shows moves left. The
   user wants the **rest of the move to carry on from the start space**.
   - Now: `MoveEnd` in `star.c` runs the sale and `ReturnToStart`, then sets
     `GwPlayer[player].moveNum = 0` and returns 1.
   - The walking loop is `PlayerMove` = **`fn_801548D8`** (the `0x80154B78` quoted elsewhere in this
     file is inside it). It calls the move-end hook with `bctrl` (about its 120th listed instruction).
     After the hook it re-reads `GwPlayer.masuId` (+0x0C) and picks the next space with `fn_802003FC`.
     Read the whole loop in `build/GP6P01/asm/auto_03_800EF6C8_text.s` first: what a non-zero return
     skips, where `moveNum` (+0x0A) is decremented, and where `masuIdPrev` (+0x0E) and `masuIdNext`
     (+0x10) are written.
   - Likely fix: keep `moveNum`, set `masuId` (and probably `masuIdPrev`) to the start space, and return
     whichever value makes the loop count the summit as the step just taken and carry on from the
     start. Check that the dice counter updates, that a player with exactly 1 move left stops on the
     start, and that a fork right after the start still works.

   **1b. Gong of Fate: the player still sinks into the ground (gong.c).** Changing the coin-gift pose
   (motion 12 to 7) didn't fix it, so the animation isn't the cause.
   - Lead: `ev_MasuHatena` (`fn_80176EA0`) calls **`mbPlayerColSnapPlayerSet(player, 0)`**
     (`fn_801582D8`) just before the board's "?" hook. It clears bit 0x20 of byte 0x4C in the player's
     collision work (`lbl_802D5C60 + player * 0x50`, pointer at +0x24). The player-collision code
     (`PlayerColOMExec`, `mbPlayerColSnapSet` `fn_80158238`, `mbPlayerColSnapGet` `fn_80158358`,
     `mbev_PlayerColSet` `fn_8015805C`) probably adjusts the model's height after the gong moves the
     player off the space and back.
   - The events that end with **`mbev_PlayerColMasuSet(player, masu, 1)`** (the rocket's landing, the
     dragon, the Star's return to the start) don't sink. The gong never calls it. Kung Fu Falls and
     Blazing Rock don't either: check whether they sink too, and give them the same fix.
   - Try: after the jump back, and again at the end, call `mbev_PlayerColMasuSet(player, gong->masu, 1)`;
     and/or `mbPlayerColSnapPlayerSet(player, 1)` before moving the player. If it's still unclear, log the
     player's position each frame with `OSReport` (`0x8009A660`, shown in Dolphin's log window) to find
     the step that changes Y.

   **1c. Kung Fu Falls: Master Koopa "jitters up and down" (kungfu.c).** The screenshot shows only his
   cloud at the top edge: he is above the frame, and his talk motion bobs him in and out of view. He is
   placed exactly as MP7 places him (ledge 66 + (100, 150, 0), facing -30) with MP7's camera
   (`CameraOnLedge`: centre ledge + (-100, 100, 0), rot (-20, 0, 0), zoom 1600).
   - Fix the framing: lower him (try ledge + (100, 50, 0)) or pull the camera back or up (zoom about
     2400, or centre y + 200). He is placed the same way in `StarPrize`. The gong uses
     `mbCameraMoveMasu` with zoom 2400/3000 and looks right.

   **1d. Blazing Rock: the flames are a huge white blob (blaze.c).** The screenshot shows a white smear
   several hundred units across over the rock.
   - Why: the flame sprite (w04 file 61, MP7 0x2E) is **I8**. MP6's particle draw (`particleFunc`,
     `src/game/hsfanim.c` around line 790) colours I8/I4 sprites only from the vertex colour, which is
     white by default. With additive blending, one quad per emitter vertex and MP7's size (500-600;
     MP6's quad is `basePos` +-0.5 times the scale), they add up to white.
   - Fix: give each flame a fire colour in `FlameHook` (for example r 255, g 120-160, b 30, alpha 0xE0).
     MP7's colours are .rodata 0x4B4 `ff ff ff e0` and 0x4B8 `60 60 60 ff` per flame, and 0x4BC/0x4C0
     per system; MP7 also sets a second sprite, 0x2F, with `0x8022C1A0(id, anim, 1)`, which may be the
     colour layer. Cut the size (start around a base of 120-150 instead of 500-600) and try normal
     blending. Log `flameNum` and check that `FLAME_RISE` (150 below the vertices) puts the flames on the
     rock. Tune with the user.
   - The smoke (file 62, MP7 0x30) is I8 too: give it a grey colour.

   **1e. Blazing Rock: lose a Star on failure (blaze.c; the user's rule, not MP7's).** After "Too bad"
   (record 27), if the player has a Star, take one with the game's own popup, as the mod's Star Trap orb
   does (`src/tools/patches/apply_star_trap_orb_patch.py`, `cave_loss`):
   `mbStarDispPlayerCreate(player, -1)` (`0x80181DDC`), then `HuPrcVSleep` until
   `mbStarDispCheck(player)` (`0x80182258`) returns non-zero, then `mbPlayerStarAdd(player, -1)`
   (`0x8015CF64`). Read the count with `mbPlayerStarGet(player)` (`0x8015CE98`) or
   `GwPlayer[player].star`. The orb calls `mbDiceFadeSet(player)` (`0x80186258`) first: check what that
   does before copying it. Update `blaze.c`'s header, which describes MP7's rules.

   **1f. Blazing Rock: 10 more presses (blaze.c).** `PRESS_TARGET` 60 to 70, so the target becomes
   70 + rand(10). Update the header comment, which says 60.

   After the fixes, update the statuses here and in the aid's docstring. Still unchecked from earlier:
   the next buyer being offered 20 coins, and the declined line.

2. ~~A lasting MP7 disassembler~~ Done (2026-11-25): `src/tools/scripts/mp7_rel_dis.py`, tests in
   `src/tests/test_mp7_rel_dis.py`, capstone added to `requirements.txt`.
3. ~~Space table for the C board~~ Built (2026-11-25): `pagoda_stub` rewrites file 42 with MP7's
   flags. The DOL only tests space flags against the board's `mbBranchMAttrSet` mask (0 here) or a
   caller's argument, so the extra bits are safe for the engine.
4. ~~Master Koopa on the summit~~ Done and confirmed in game (2026-11-25). House and
   sign added after the first test. Left out: MP7's sounds, the house's particle and the sign's roll
   animation after a purchase (section 1 `0x1F8C`).
5. **"?" spaces:** the hook and dispatcher are in `board.c`; the Gong of Fate (`gong.c`) and the
   bottle rocket (`rocket.c`, a simpler flight than MP7's, confirmed) and Kung Fu Falls (`kungfu.c`,
   a full port), Blazing Rock (`blaze.c`) and the dragon (`dragon.c`, space 44) are built: every "?"
   space now has its event.
6. **Bowser Time and the bridges: built (2026-11-25), not yet tested in Dolphin.** `bowser.c`; files 66–78
   (Bowser = MP7 `capsulechar1.bin` (data dir 0x1D) 0 + motions 1, 2, 8, 5, 0x10, 6, 0x11, 0xA, 0xB; bridges
   = MP7 `w02.bin` 0x1D intact / 0x1E breaking / 0x1F broken), test `tests/test_pagoda_files.py`.
   - **MP7's design:** `.data 0x480` is MP7's Bowser Time table `{0x156B4, 100}, {0x15F00, 100}, 0`,
     registered at `.text 0x560` with an engine setter (MP6 has no Bowser Time; the matching MP6 slot
     `fn_8014BDEC`/`lbl_802DD498` is something else). The gauge rises 20% per turn's minigame
     ([mariowiki](https://mariowiki.com/Bowser_Time)), so every 5 turns. The repair `0x152AC` runs from a
     per-round hook registered at `.text 0x44C`.
   - **Bridges:** setup `0x13E90`: three models per bridge on the map's `h_bridge0..2`; bridge b's spaces are
     flag indices 2b+1, 2b+2 under 0xE00000 (25/24, 29/30, 33/34, colour 0); the broken mask is bits 5–7 of a
     saved byte. Broken: MP7 sets type 0x2000 on the first space (MP7 `0x8018050c` = OR, `0x80180538` =
     ANDC on masu +0x10) and 0x40 on both (`0x801812f4`). **Not copied:** MP6's `ev_Branch` (`fn_801EEA34`)
     filters links by the type mask and, with no candidate left, returns an uninitialised stack slot.
     Instead `star.c`'s move-end hook calls `PagodaBridgeBlocked` first: stepping onto a broken bridge's
     first space shows record 35, hops back to `masuIdPrev` and ends the move.
   - **Port:** the turn-init hook (`mbPlayerTurnInitHookSet`, `fn_801537D8`, called in `PlayerTurn` before
     the dice) handles each new `GwSystem.turnNo` once (last turn kept in `boardWork[0]` bits 8–15; broken
     mask bits 2–4): repair (record 36) if anything is broken, then on turns 6, 11, 16 … the bridge event
     (32, 33, Bowser's jump, the crash through a random bridge, 34, 35). **Every 3 turns** (turns 4, 7,
     10 …; the user's choice, MP7 is 5): `BOWSER_TIME_EVERY` in `bowser.c` (1 = every turn from turn 2).
   - **To check in Dolphin:** the bridges show on the map (they weren't drawn before: the MP7 map hooks them);
     Bowser's size and the summit camera (`SUMMIT_ZOOM` 1500, MP7 900); the crash; a player stopped at the
     broken bridge; the repair next turn.
   - **Left out:** debris particles (sprite `0xFE0034`, processes `0x14360`/`0x147D8`), music (MP7 track
     0x16), sounds, the speaker portrait (MP7 speaker 7).

   **6b. Bowser Time's stomp event: built (2026-11-25), not yet tested in Dolphin.** `StompEvent` in
   `bowser.c`; Bowser Time picks it or the bridge 50/50 (MP7's weights 100/100).
   - Bowser (32, 37) jumps to the space flagged index 2 under 0x180000 (space 71) and stomps, then the start;
     players on those spaces get the stun motion. Then `KnockDown` moves **every** player whose space has a
     **masu layer 1** link one ledge down along it (48-frame arc, 750 high), one at a time with the camera
     on them; Bowser says 38.
   - Layer 1 = MP7 `w02.bin` file 1 (each real space → the space on the ledge below; 27/26/28/23/22/21/17/19
     → the start), appended as `w04*.bin` file 79 (`FILE_SPACES_BELOW`) and loaded in `board.c` exactly as
     MP7 (`.text 0x154`) and Towering Treetop (`w01Dll`) do: `mbMasuLayerSet(1)`, `mbMasuDataRead`, restore.
   - MP7's motions `0xBC0011`/`0xBC0012` (dir 0xBC = `mariomot.bin`) are byte-identical to MP6
     `<char>mot.bin` 18/19, used as `P01_DATA_mariomot | 18/19`; no new files.
   - To check: who gets knocked and where they land; the stomp camera (`STOMP_ZOOM` 2500, MP7 2000).
7. **The flight back down: built (2026-11-25), not yet tested in Dolphin.** `ReturnToStart` in `star.c`,
   from MP7 `0x115A8`: camera `mbCameraMoveObj(player obj, (-35,0,0), zoom 2400)` (MP7 2000; it sets the
   follow target), the cloud (file 54) spirals in onto path point 0 (120 frames, 720°, 400 out, 800 up), the
   player hops on, 300 frames along the Bézier through MP7's 18 points (`.data 0x2A0`, summit → start), hops
   off onto the start, the cloud flies on 2000 and up 400 (60 frames), then `mbCameraFocusObjSet(-1)`.
   MP7's boarding helpers (`0x80164EAC`, `0x80164AFC`, missing in MP6) are plain hops; no trail particle.
   To check: the camera follows, the player stays on the cloud, the landing on the start.

   **7b. The leaps across the gaps: built (2026-11-25), not yet tested in Dolphin.** `gaps.c`. Players used to
   walk through the air at two gaps (the user's clip of MP7 shows the bamboo bounce). MP7's move-end hook
   (`.text 0xE78`) runs `0x124B8` for space flag 0x8000 (space 82 → 83) and `0x135E8` for 0x2000 (86 → 75).
   - Bamboo: three poles (MP7 `w02.bin` 9 → file 80) on the map's `h_bamboo0..2`, paused; jump (24 frames) to
     each pole's `h_cha` joint × the map joint matrix taken at setup, the pole springs (motion from 0, speed 1),
     rumble; then 30 frames onto 83.
   - Branch: MP7 `w02.bin` 0xA → file 81 (own placement), paused; jump (30 frames, arc 300) to hang at
     `h_branch` + (0, −90, −60) turned to the heading, swing 42 frames (speed 0.7) following the joint, fling
     (30 frames, arc 600) onto 75.
   - `star.c` `MoveEnd` calls `PagodaGap` after the bridge check and returns 1 (82/83/86 are colour 0).

# History: the two experiments (research record)

---

## Experiment 1: Pagoda Peak's spaces with Snowflake Lake's rules
**Goal:** board 11's players walk Pagoda Peak's real paths over Pagoda Peak's map, with ordinary
spaces working (blue, red, "?" and so on), a start space and Star spots. Snowflake Lake's own
events are switched off where they would break.

### Research (read-only), done first
1. **How `w04Dll` loads spaces.**
   - At .text 0x18C–0x194 it picks a base, `r28 = 0xE90000` (w04) or `0xEA0000` (w04n), then
     `mr r3, r28` at 0x190 and `bl mbMasuInit` (`fn_801748EC`), which loads file 0. That's the
     candidate site.
   - Confirm that no other call loads file 0: grep `w04Dll` asm for `mbMasuInit` and for other
     users of the masu table.
2. **What Snowflake Lake's flags mean.** For each flag bit in `w04.bin` file 0
   (`python -m tools.scripts.masu_dump w04`), find the code that tests it. Search `w04Dll` and the DOL
   board engine for flag reads (accessor `fn_80176FCC` = flags, `fn_80176F84` = type,
   `fn_80176F54` = masu pointer; masu stride 0x70, flags at masu+0x14, see `masu_dump.py`). The known
   generic ones from the patching guide §7: start = 0x40 on Faire and Castaway, plus the flags this
   mod has claimed. Produce a table: bit → meaning → who reads it.
3. **What Pagoda Peak's flags mean.** The same search in MP7's `w02dll.rel` and MP7's DOL. MP7 has
   no symbols, so match functions by shape against MP6's (MP7 is built on MP6's engine). The aim is
   only to identify the start space and the Star spots; the event triggers can stay unknown.
4. **Space type 0x100 and colour 11:** find what they are in MP7, and decide a safe MP6 value (for
   example 0 or blue).
5. **Which MP7 table to use** (file 0 or 2, and what 1 and 3 are for). Dump all four with
   `masu_dump`'s loader and compare positions and links.
6. **Snowflake Lake's events that use space ids or flags** (its gimmicks, Star logic, the DK and
   Bowser capsule events, which are board-3 special cases in the DOL). List what to switch off or
   remap for board 11.

### Build (new test aid `mp7_spaces_test`, after `mp7_map_test`)
- **Convert the table.** Take MP7 `w02.bin` file 0 (or 2) and rewrite its flags into w04's
  meanings: the start space flag, Star-spot flags, and nothing else. Map colour 11 and type 0x100 to
  safe values. Use `tools.lib.boards` (`load_spaces`; `replace_file0` shows how to LZ-pack and write
  file 0). The MP7 file goes in raw (decode type 1) or zlib; check that `mbMasuInit` accepts
  decode type 7, or LZ-encode it.
- **Add it** to `w04.bin` and `w04n.bin` as file 42 (after the map's 41), backed up to `backups/`,
  in the same style as `src/tools/patches/test_aids/apply_mp7_map_test_patch.py`.
- **Point `w07dll.rel` .text 0x190** `mr r3,r28` (`7F83E378`) at `ori r3,r28,42` (`6383002A`).
- **Switch off** the Snowflake Lake events that research step 6 found unsafe: hooks in `w07dll.rel`
  only (`tools.lib.rel.check_words`, `add_calls`), never in `w04Dll.rel`.
- **Optional, if the camera or space markers float:** check whether space Y positions need an offset.

### Verification
- Run `pytest` and `ruff`. Run the aid twice and compare hashes. `--off` restores the archives to 42
  files and the REL to `mr r3,r28`.
- `masu_dump`-style check of the new file 42: 88 spaces, links intact, exactly one start space, Star
  spots flagged.
- **In Dolphin**, build with `clone_board_menu`, `mp7_map_test` and `mp7_spaces_test`, deploy, run
  `build_iso`, then start Snowflake Lake's icon. Check:
  - the players start on Pagoda Peak's start space and walk its paths
  - landing on blue and red spaces works
  - the Star appears on a Pagoda Peak spot and can be bought
  - a short game reaches the results screen
  - the real Snowflake Lake is unchanged

### Result (2026-11-24): research done, aid built, not yet tested in Dolphin
Test aid `mp7_spaces_test` (`src/tools/patches/test_aids/apply_mp7_spaces_test_patch.py`, tests in
`src/tests/test_mp7_spaces.py`). Its docstring has the details. In short:
- **Load site:** `w04Dll` .text 0x190 is the only `mbMasuInit` call. The aid makes it `ori r3,r28,42`.
- **Type (+36) is engine-wide** and matches between the games. 0x8000 = start (one per board; MP7 space
  37), 0x8 → 0x4 = climb pairs, 0x20 = shop model node, 0x2000 = side node. The default "never a stop"
  type mask is 0xA020 (`fn_801EF3D0`); boards add bits through `fn_801EF38C` (type) and `fn_801EF39C`
  (flags). MP7's 0x100 (summit only) isn't tested by MP6 code, so it is cleared.
- **Flags (+38) are board-defined.** Snowflake Lake's REL finds every space by flag, never by id:
  - Snowflake Lake has no Star Space. Its Chain Chomp stations are the 3-bit index under 0x380
    (`fn_80177014` packs it: 0x80 = 1 … 0x200 = 4), each linked to a type-0x2000 node where the
    Chomp's house stands.
  - `fn_1_C04` (the move-end hook) offers the Chomp ride: 20 coins by day, 10 at night (MP6 message bank
    0x32, "Wooooof! (What's up? Want a ride?)").
  - `fn_1_1D74` builds one station per index and needs indices 1..count.
  - The aid puts one station on the summit (54). That's where the Chomp appeared in the user's test,
    because Snowflake Lake's code still runs this board.
  - Everything else is gimmicks. With no gimmick flags set, their hooks never fire and their setup
    counts 0 spaces.
- **Colours:** 0–10 match. MP6's colour tables (`0x80265408`/`0x80265460`) don't cover 11 in both
  modes, so MP7's colour 11 becomes blue.
- **Board-3 cases in the DOL** (`ev_CapDonkeyStart`/`ev_CapKoopaStart`) only change a roulette's option
  count. They use no space ids.
- **MP7 tables:** file 0 is used. File 2 is the same graph with 10 colours changed; files 1 and 3 are a
  bare graph with other links.
- **Layout:** one trail, start 37 → summit 54 (Star, stand 73) → 74, a dead end. MP7's REL sends players
  back down. The aid links 74 → 27, so players walk straight from the summit to the bottom (a stopgap).
  Spaces 71 and 72 are unreachable MP7 event points, kept as they are.

---

## Experiment 2: decide how Pagoda Peak gets its own board code
**Goal:** choose between two routes for Pagoda Peak's events (the single trail up the mountain,
the top of the mountain, its event spaces) with evidence, not guesses. This experiment is research
plus a proof of concept; the full event port is the milestone after it.

### Route A: run MP7's `w02dll.rel` in MP6 by remapping its calls
MP7's REL calls MP7 DOL functions through module-0 relocations to MP7 addresses. Remap each target
to the matching MP6 function, the same idea as `src/tools/closecall/p01_names.py`, which maps US to
PAL symbols.
1. **Inventory.** Walk MP7 `w02dll.rel`'s module-0 relocations (`tools.lib.rel.walk_relocs`,
   `import_blocks`). Count the distinct MP7 target addresses (functions and data), and separate code
   targets from data targets (GwSystem, globals, tables).
2. **Match.** For each MP7 code target, find the MP6 PAL function with the same code. Compare
   function bytes, masking out relocated fields (branch targets, `lis`/`addi` pairs), and use size as
   a first filter. MP6 PAL functions come from `src/config/GP6P01/symbols.txt`. Data targets
   (GwSystem `0x80283290` in MP6, and so on) map by meaning.
3. **Coverage report.** Exact matches, near matches (small differences), and missing (MP7-only
   features). This decides Route A: high coverage plus a small missing set means remapping is
   viable.
4. **Proof of concept if coverage is good.**
   - Rewrite one REL's relocations to MP6 addresses, write it as `w07dll.rel`, keep `li r3,11`, and
     point it at MP7's own data (`w02.bin` added as a new data dir entry 261, with the data-dir table
     moved: 3 references, see `board-tables.md`).
   - Its message bank needs to be MP7's bank appended to MP6's messages.
   - Expect crashes. The result to aim for is "loads and reaches the opening", then fix forward.

### Route B: write a new Pagoda Peak REL in C
Copy the Close Call precedent: `src/tools/closecall/build_closecall_rel.py` builds
`src/src/REL/closecallDll/*.c` against PAL symbols (`p01_names.h`) with mwcc, then makes it with
`dtk rel make`.
1. **Find the minimum a board REL must do.** Read the smallest MP6 board REL (`w10Dll` or `w01Dll`)
   to list what its prolog and init do: `mbObjectSetup(boardNo, init, end)`, `mbObjDirSet`,
   `mbMasuInit`, the map model, the camera, the Star logic and event hooks.
2. **Write a stub board in C** that only loads Pagoda Peak's map and spaces (from experiment 1) and
   uses generic engine behaviour (ordinary spaces, Star, shop) with no special events. Build it as
   `w07dll.rel` through a build script modelled on `build_closecall_rel.py`.
3. **Size the event work** from MP7 `w02dll`'s function list: how many functions are events and
   what each does.

### Decision
Do Route A's inventory and coverage first (one session, read-only). Then:
- If at least about 90% of the code targets match, try Route A's proof of concept.
- Otherwise go to Route B: generic board code in C, with Pagoda Peak's events rewritten one by one.

### Verification
- The coverage report goes in `plans/pagoda-peak/route-a-coverage.md`, listing each MP7 target
  with its MP6 match or "missing".
- **Route A's proof of concept,** in Dolphin, the log shows `DLLStart 112` and the REL links; then
  find how far it gets (opening, first turn).
- **Route B's stub** builds with the repo's mwcc setup; in Dolphin, board 11 loads Pagoda Peak's map
  and spaces and plays as a plain board.

### Result (2026-11-24): Route A ruled out, go to Route B
**Route A inventory** ([route-a-coverage.md](route-a-coverage.md), generated by
`python -m tools.scripts.mp7_rel_coverage w02dll`):
- **Size:** MP7 `w02dll.rel` has 2132 calls to 300 DOL functions, plus 294 data relocations to 8
  addresses.
- **Order:** both DOLs link the engine in the same order, so 104 unique exact matches anchor the search.
- **Coverage:** 142 functions (47%, 47% of call sites) match exactly, 96 are near and 62 are missing.
  That is far below the 90% bar.
  - Part of the shortfall is the compiler: MP6 spills arguments to the stack where MP7 doesn't.
  - Part is real: MP7 `0x80161000`–`0x8016D100` (about 60 targets) is a reworked player and turn
    layer. For example, its model wrappers index a player array at `0x8030C960` with stride 0x84,
    where MP6 uses `0x802D5C60` with stride 0x50.
- **Data is the blocker.** The REL reads DOL structs inline, so remapping addresses isn't enough:
  - `0x802B3798`, 67 pairs: the player array (MP6's `GwPlayer` is `0x80282E70`). Its stride is 0x110
    (MP6: 0x108), and the field offsets seem shifted: +0x0E is the most used, where MP6's `masuId`
    is +0x0C.
  - `0x80315C70`, 25 pairs: a per-player work struct (stride 0x134) with no known MP6 counterpart.
  - `0x802B4018`, 29 pairs: probably `GwSystem` (`0x80283290`).
  - Every one of these accesses would need its instruction rewritten. The MP7 decomp's
    `include/game/gamework.h` isn't at the expected path (404), so MP7's layouts aren't known.

**Route B, step 1: what a board REL does** (`w04Dll` `fn_1_F4`; `w11Dll`, the smallest board REL
at 12 KB, has the same skeleton):
- `_prolog` sets some `GwSystem` flags, then calls `mbObjectSetup(boardNo, init, kill)` (`fn_8014A554`).
- `init` makes these calls in order:
  1. `fn_800414E4` (sound group; w04 passes 0x19).
  2. `fn_80168E9C(day dir, night dir)` (`mbObjDirSet`).
  3. `mbMasuInit` (`fn_801748EC`).
  4. `fn_801C15A0(dir|2)`.
  5. The map and scene models: `fn_801687F4(dir|n, 0, 0)` plus `fn_801695F4` / `fn_80168F60` /
     `fn_801698A0` (attributes and motions).
  6. The camera: `fn_80170AA0(0)`.
  7. The hook registrations (names from the US symbols in `p01_names.h`). The engine checks each for
     NULL, and `mbMasuInit` clears the space hooks:
     - `mbev_MasuMoveEndSet` (`fn_80179A0C`): fires as a player steps onto each space; Snowflake Lake
       offers its Chain Chomp ride here.
     - `mbev_MasuMoveStartSet` (`fn_80179A14`) and `mbev_MasuHatenaSet` (`fn_80179A1C`, "?" spaces).
     - `mbOpeningInstHookSet` / `mbOpeningStarInstHookSet` (`fn_80191068` / `fn_80191070`), and the
       opening and map cameras `mbOpeningViewSet` (`fn_8018F5B0`) / `mbMapCameraSet` (`fn_8017461C`).
     - `mbev_ShopInit` / `mbev_ShopExInit` (`fn_801E93BC` / `fn_801E93F0`): the shopkeeper model,
       placed at each colour-9 space's type-0x20 node.
     - `mbLightFuncSet` (`fn_8014BBE4`), `mbev_NextTimeSet` (`fn_8014BDC4`, the day/night switch),
       `mbPlayerTurnInitHookSet` / `mbPlayerTurnCloseHookSet`, `mbBranchComStarHookSet` (CPU forks),
       `mbMapHookSet`, `mbScrollHookSet`.
  8. The board's own object setup.
  9. `fn_800097F8(dir)`.
- **The Star** is the board's own code: no two MP6 boards share a Star routine. (Snowflake Lake has no
  Star Space at all; its `fn_1_1D74` / `fn_1_C04` / `fn_1_21EC` are the Chain Chomp stations.) So
  Pagoda Peak's Star has to be written for the C board.

**Route B, step 3: size of the event work.** MP7 `w02dll` has 0x1BC3C bytes of text and about 185
functions (168 stack frames, 190 `blr`). That's about 1.6× Snowflake Lake's (126 functions, 0x10D58
bytes). 51 of them are reached through pointers (hooks and callbacks), which is where the events
start. They haven't been classified yet.

**Route B, step 2: stub v1** (2026-11-24, built, not yet tested in Dolphin). It's in
`src/REL/w07Dll/board.c`, built by `tools/pagoda/build_pagoda_rel.py` (Close Call's toolchain) and
installed by the test aid `pagoda_stub` (`--off` puts the clone back).
- **What it does:** Snowflake Lake's init skeleton with Pagoda Peak's spaces (file 42) and map (file
  41), Snowflake Lake's shopkeeper (files 5/6/8) and its opening and map cameras. The REL is 1900 bytes,
  and all 30 call targets resolve to the intended PAL functions.
- **Not in it yet:** Pagoda Peak's Star, "?" spaces, day/night visuals, the opening's Star intro and
  the orb-throw collision model (`mbCapThrowColCreate(-1)`).
- **v2: Pagoda Peak's own Star** (2026-11-25, built, not yet tested in Dolphin). Rules from MP7 bank
  0x14: Master Koopa sells a Star at the top (space 54). The price starts at 10 coins and goes up by 10
  per purchase, to 40. After the summit MP7 carries the player back to the start.
  - **Source:** MP7 `w02dll` .text `0x100C4` (the sale; it uses messages `0x140007`–`0x14000D`) and
    `0x115A8` (the trip back down: `w02.bin` file `0x26` carries the player along a spline to the
    start space found with `mbMasuFind_AttrIdGet(-1, 0x8000)`).
  - **Port:** `src/REL/w07Dll/star.c`, on the move-end hook (`mbev_MasuMoveEndSet`, which gets
    `(player, masuId)`; returning 0 lets the move go on). It uses MP6's own calls, as Castaway Bay's
    and Snowflake Lake's RELs do: `mbWinCreate` / `mbWinCreateChoice` / `mbWinInsertMesSet` (name and
    price) / `mbWinWait` / `mbWinChoiceGet`, `mbComChoiceUpSet` (CPU players buy), `mbPlayerCoinGet`,
    `mbCoinAddDispExec(player, -price, 1, 0)` and `mbStarGetExec`.
  - **Price level:** bits 0–1 of `GwSystem.boardWork[0]`.
  - **Text:** the test aid appends MP7 bank 0x14 (all 57 records, all six languages) to MP6 bank 0x32
    as records 26–82 (`PAGODA_MES(n)` in `pagoda.h`). `tools/pagoda/mp7_text.py` converts each record:
    MP6 window-size headers (the rule matches 231 of MP6's 259 board records) and MP7's coin icon
    dropped.
  - **Return to the start** (2026-11-25, built): after every visit, as in MP7, the screen fades out, the
    player is moved to the start space with the debug warp orb's calls (`masuId`, `mbPlayerPosSetV`,
    `mbev_PlayerColMasuSet`) and the move ends: the hook sets `moveNum` to 0 and returns non-zero
    (`PlayerMove` at `0x80154B78` skips the step count and stops at 0 moves). The 74 → 27 link is no
    longer walked.
  - **Not yet:** Master Koopa's model and motions, MP7's camera moves and sounds, and MP7's flight back
    down (`w02.bin` model `0x26` along a spline).
  - **Later events, same bank:**
    - the bottle rocket (records 0–6)
    - the Gong of Fate (18–23)
    - Kung Fu Falls (14–17) and Blazing Rock (24–31)
    - Bowser Time and the bridge (32–38)

## Rules to keep (from AGENTS.md)
- Addresses are PAL; use `P01_DATA_*` for data dirs.
- Patches are idempotent: read the current output, else the original.
- New steps go in `STEPS` with a comment and a row in `src/tools/README.md`'s dependency table.
  Test aids go in `TEST_AIDS`.
- Board files are edited in `root/data` with backups in `backups/`; never overwrite a backup.
- In-game results only count once the user confirms them; update each script's status note then.
- Don't commit or push; the user does that.
