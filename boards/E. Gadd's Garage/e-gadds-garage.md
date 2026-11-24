# E. Gadd's Garage (w02Dll) - investigation notes

Investigation only: nothing here has been patched or run in Dolphin, and no existing `apply_*_patch.py` touches w02, bank 0x30 or `w02*.bin`. Everything below comes from `masu_dump`, the REL assembly and message bank 0x30. Items marked **unverified** are inferences. The method and patch conventions (build/deploy, caves, message editing, the `apply_*_patch.py` pattern) are the same as for Faire Square, see `boards/faire-square/faire-square.md`. `full-board.png` in this folder is the overhead map.

## Where things are
- REL: `src/build/GP6P01/w02Dll/asm/auto_00_00000000_text.s` (~27k lines). Listing columns: first = REL `.text` offset, second = file offset (`.text` + 0xDC). Config: `src/config/GP6P01/rels/w02Dll/`. No C source.
- Space data: `root/data/w02.bin` (day) and `w02n.bin` (night), file 0, 113 spaces. **Day and night are identical** (type, flags, kind and links). Dump: `cd src/tools && python -m tools.scripts.masu_dump w02` (the kind is the `extra` field of `masu_dump.load()`).
- Text: **message bank 0x30 (48)**, 27 records (0x300000-0x30001A). Every event uses speaker id 0xE (E. Gadd).
- `GwSystem.boardNo`: probably **1** (Faire Square w03 = 2). **Unverified**: check it before writing any boardNo-gated DOL patch.
- Decomp names for P01 addresses: `src/build/GP6P01/include/p01_names.h` (e.g. `#define mbev_MasuHatenaSet fn_80179A1C`).

## Hook registration (`fn_1_F4`, board init)
| DOL setter | REL callback | role |
|---|---|---|
| `mbev_MasuHatenaSet` (0x80179A1C) | `fn_1_387C` | **landing** dispatcher (green "?" spaces, kind 3) |
| `mbev_MasuMoveEndSet` (0x80179A0C) | `fn_1_39F4` | **passing**, runs on every step (cosmetic only on this board) |
| `mbev_MasuMoveStartSet` (0x80179A14) | `fn_1_39EC` | returns 0 |
| `mbev_MasuLinkTblHookSet` (0x80179A24) | `fn_1_3AF4` | returns 0 |
| `mbPlayerTurnInitHookSet` | `fn_1_3AFC` | shows a model again and clears the 0x1378 flag |
| `mbMapHookSet` | `fn_1_3B44` | hides/shows the teleporter models in map view |
| `mbOpeningInstHookSet` | `fn_1_30F4` | intro help, message 0x30001A |
| `mbStarMoveHookSet` | `fn_1_1572C` | moves the Star |
| `mbBranchMAttrSet(0x502)` (`.text` 0x19E4) | - | flags that the path chooser skips |

Hook points for new events (the same trick as on the other boards, module-0 call through `battle_port.add_calls`):
- **landing exit** `li r3,1` at `.text` **0x39C8**: r30 = player, r31 = space, and every branch of `fn_1_387C` reaches it;
- **passing exit** `li r3,0` at **0x3AD4**: r29 = space;
- **init tail** `bl mbMapCameraSet` at **0x1B44**.

## Landing events (`fn_1_387C`, flag -> handler)
| flag | spaces (* = kind 3) | handler | event |
|---|---|---|---|
| 0x1 | 45*, 49*, 70* | `fn_1_8C9C` | **Teleporter** (see below) |
| 0x800 | 36*, 38* | day `fn_1_B11C` / night `fn_1_B334` | **Shuffle-o-tron** by day, **Orb Morpher** by night (see below) |
| 0x1000 | 78, 79* | `fn_1_E074` | **Wealth Suckage Apparatus** (see below) |
| 0x20000 | 43* | `fn_1_13708` | **Calamity Launcher** (see below) |
| 0x40 / 0x80 / 0x200 | belts: 63-66 (63*) / 61-62 (61*) / 51-54, 56 (54*) | `fn_1_6CFC(0/1/2)` -> `lbl_1_data_874`: `fn_1_4FB0`, `fn_1_544C`, `fn_1_58E8` | **Conveyor belts** (see below) |

- **Teleporter** (messages 0-3):
  - Free to use. Options: Sure / No / View board. Message 1 is the repeat-visit wording (flag at `bss_4`+4).
  - Each teleporter's pod is its linked flag-0x2 node (100, 101, 102), found with `fn_1_A4B4`.
  - Destinations come from the table `lbl_1_data_A84` = {2, 0, 1}: **45 -> 70, 49 -> 45, 70 -> 49**. **Unverified**: this assumes `fn_1_89A8` builds the pod list in id order.
  - CPUs compare the distance to the Star (`fn_80178B60(space, 7)`) from here and from the destination, then answer with `mbComChoiceUpSet`/`DownSet`.
- **Shuffle-o-tron** (day, messages 4-8): rerolls the player's orbs (`fn_1_B570`, which uses `mbCapListCopy` and `frand`). Result line: message 5.
- **Orb Morpher** (night, messages 9-13): sells orbs for coins (`mbCapSellCostGet`). Message 10 is "You get %d coin".
- Both have a "no orbs" line: message 8 (Shuffle-o-tron) and message 13 (Orb Morpher).
- **Wealth Suckage Apparatus** (messages 14-18): steals coins from the rivals, who mash A to keep them ("Tap A to hold on", message 14). The dispatcher does not check day or night, so it is the same in both.
- **Calamity Launcher** (messages 19-25): pay coins to have 1-5 **new** orbs launched onto board spaces in your name. Your own orbs are not used. Message 20 is the price menu, with `%d` arguments. Full flow in "Calamity Launcher in detail" below.
  - Prices: table `lbl_1_data_C64`, 4 rows of 5 words, row = the player's rank (`GwPlayer+9` bits 4-5, the same field the orb lists use).
  - The rows (coins for 1-5 orbs): 1st 10/30/60/100/150, 2nd 10/25/50/80/120, 3rd 10/20/40/60/90, 4th 5/15/30/50/75.
- **Conveyor belts** (`belthook1-6`): landing on a belt's "?" runs that belt and carries the players standing on it (`mbMasuNextDispSet`, `mbRandMod`, `omVibrate`). The handler then waits with `mbev_CapPlayerIdleWait`.
  - Belt spaces have type 0x10-0x12.
  - Table entries 3 and 4 (`fn_1_5D6C`, which is capsule-related, and `fn_1_6378`) are used by other callers that have not been traced.

## Other flags (no landing event)
- **Bits 2-5 (mask 0x3C) = 1..14: central turntable.** Spaces 24-30, 55-60 and 96 are attached to the joints `ghook00-13` of the turntable model (data 0xE50014/0xE50015 by day, 0xE60014/0xE60015 by night). `fn_1_3CC8` builds it. `fn_1_4020` rotates it and carries the players; it is started from `fn_1_3FB8` by the day/night time-change sequence `fn_1_31D8`. So the cross presumably turns at each day/night change (**unverified**; its centre is at about (0, -2949)).
- **Bits 18-20 (mask 0x1C0000) = 1..5: Star locations.** Spaces 71 (1), 83 (2), 90 (3), 46 (4), 26 (5). `fn_1_15D7C` reads the field. `fn_1_1572C` places the Star (`mbMasuTypeSet`, `mbStarMasuNextSet`) using a rotating list at `bss_4`+0xE.
- 0xC000 field (31 = 3, 32 = 2, 33 = 1): pistons and steam (`pistonhook`, `steamhook`). Cosmetic, animated in the per-frame code `fn_1_1BD8` and the pass handler. Sound 0x59B.
- 0x10000 (space 14): a model animates and sound 0x5AF plays when a player passes. Cosmetic.
- 0x2 (100-102): teleporter pod nodes, no links.
- 0x400 (103, 104) and 0x100 (105, 106): an uncounted path 56 -> 103 -> 104 -> 105 -> 106 -> 6, probably the big green pipe (not traced).
- **Free flag bits: 0x200000 and above.** The bits 0x8 and 0x20 are part of the 0x3C turntable field, so do not use them.

## Space kinds (`extra`)
- 1 blue: most spaces.
- 2 red: 4, 14, 20, 33, 51, 53, 65, 85, 113.
- 3 "?": 36, 38, 43, 45, 49, 54, 61, 63, 70, 79.
- 4 miracle: 58. 5 duel: 24. 6 DK/Bowser: 87, 91.
- 8: 5, 21, 32, 42, 50, 67, 75 (probably orb spaces, **unverified**).
- 9 item shop: 10, 86.
- 0: markers, junctions and the turntable/belt helper nodes.

Types:
- 0x8000 on space 1: probably the start, as with Castaway's 0x8000 node.
- 0x8 -> 0x4 pairs 19 -> 97 and 40 -> 39: ladder ends (y changes by about 600).
- 0x2000: hidden nodes 107, 109-111. 0x20: 98, 99 (no links).

## Message bank 0x30 index
| records | event |
|---|---|
| 0-3 | Teleporter |
| 4-8 | Shuffle-o-tron |
| 9-13 | Orb Morpher |
| 14-18 | Wealth Suckage Apparatus |
| 19-25 | Calamity Launcher (20 = price menu) |
| 26 | board help (Star costs 20 coins, the Star moves, rare orbs) |

## Candidate patch points
- **New landing events:** hook `.text` 0x39C8, use a free flag bit (0x200000+) and tag the space in both `w02.bin` and `w02n.bin`.
- **Kind edits** (e.g. blue -> DK/Bowser or miracle): as in `apply_faire_square_dk_bowser_space_patch.py`.
- **Data-only tweaks:** teleporter pairing (`lbl_1_data_A84`), Calamity prices (`lbl_1_data_C64`), the Star-spot field on spaces.
- **Cave space:**
  - DOL section 16 (0x802F7DA0-0x802F8DA0) has about 0xB20 bytes left after the Castaway patches; a new section is the alternative.
  - Check the cave list in the Faire note before choosing an address.
- **Board gate:** DOL-side changes need a boardNo gate (assumed 1).

## Open questions
1. Confirm boardNo = 1, and that space 1 is the start.
2. Map the space ids to `full-board.png` (in Dolphin, or from the belt and turntable geometry).
3. Trace belt entries 3 and 4 (`fn_1_5D6C`, `fn_1_6378`) and the 103-106 pipe path.
4. Confirm the `GwPlayer+9` field that selects the Calamity price row.

## Wheel o' Fortune (space 7, `src/tools/patches/apply_egadd_wheel_patch.py`, not run in Dolphin)
The Castaway wheel (`boards/castaway bay/castaway-bay.md`, "Wheel o' Fortune") brought here, same behaviour.

**Where and when**
- **Space 7** is the blue space at the left end of the bottom-right conveyor. The path runs: star pad 1 -> 3 -> 4 red -> 5 orb ring -> **7** -> 6 platform.
- It fires on every pass (walking past or stopping on it), automatically, for humans and CPUs.

**Outcomes** (25% each, forced onto the slice that was rolled):
- a random orb from the Castaway pool, or a "pockets full" line;
- +10 coins;
- -10 coins (a "no coins" line at 0);
- teleport to a random kind 3-6 space with **no exclusions**: 24, 36, 38, 43, 45, 49, 54, 58, 61, 63, 70, 79, 87, 91. The arrival runs that space's landing event (teleporter, Shuffle-o-tron, belts, Calamity...).

**Space data**
- **Trigger: flag 0x200000** on space 7 in `w02.bin`/`w02n.bin`. Backups: `backups/w02*.bin.bak_before_egadd_wheel`.
- 0x4000, which Castaway uses, is taken here: it belongs to the piston field 0xC000.

**Hooks**
- **Pass:** w02Dll `.text` **0x3A0C** (`mr r29,r4`, near the start of `fn_1_39F4`). It becomes a module-0 call to `0x802F8800`, which runs the shared Castaway pass body (`apply_castaway_wheel_patch.pass_body`) with r30 = player and r31 = space, then does `mr r29,r31`.
  - The exit at 0x3AD4 could not be used: `fn_1_39F4` drops the player argument before it.
- **Init:** `.text` **0x1B44** (`bl mbMapCameraSet`, last call of `fn_1_F4`) is retargeted to `0x802F8D00`. That cave creates the wheel model (`capsule.bin` 0x140056) at `WHEEL_POS` (-399, 76, 1), 225 above the space as on Castaway, then makes the original call.

**Caves** (DOL section 16, after the troll; ends 0x802F8D70, 0x30 bytes before the section end):

| cave | address |
|---|---|
| show | 0x802F87C0 |
| pass | 0x802F8800 (hold floats at +0x100) |
| outcome | 0x802F8920 |
| teleport | 0x802F8A60 |
| model | 0x802F8BE0 |
| turn | 0x802F8C80 |
| init | 0x802F8D00 |
| data | 0x802F8D50 |

Reused unchanged: the Castaway spin cave `0x80230B00` (it swaps the Castaway icons in and Faire's back), the random orb routine `0x80231040`, the icons in `board*.bin` 185-187, and the model.

**Text:** bank 0x30 records 27-33 (intro, 4 outcome lines, pockets full, no coins). These are the Castaway lines, spoken by E. Gadd (speaker 0xE), English in every language file.

**Shared code:** `apply_castaway_wheel_patch.py`'s builders now take parameters (bank, speaker, flag, exclusions, cave addresses). The Castaway output was checked to be byte-identical after the change.

**Tested:**
- unicorn emulator with the game calls stubbed:
  - no flag: nothing runs, r29 = space;
  - each slice, the pockets-full and no-coins cases, the teleport destination and masuId, the message ids;
  - registers and stack are intact;
  - init: model first, then the original call with its arguments.
- the script run alone, re-run, and via `apply_all.py --from egadd_wheel`: no changes on the re-run.

**Unverified in Dolphin:** the wheel's height and visibility above the conveyor; the camera; the teleport arrivals into belts and the turntable; that the pass hook also fires on the final step.

## Calamity Launcher in detail (`fn_1_13708`, space 43, read from the assembly)
1. **Arrival:** the cannon models are loaded (`mbBGRead`) and the player walks over to the launcher. Then message 19: "<name>, behold the fury of the glorious Calamity Launcher! Pay coins to set nasty Orb traps all over my garage!"
2. **Checks:** it counts the valid target spaces, i.e. every space where `mbCapThrowMasuCheck(id)` is true (call this count V).
   - If coins < the 1-orb price for the player's rank: message 22 ("Bah! You don't have enough coins") and the event ends.
   - Else if V = 0: message 21 ("Sorry, kid! There aren't any good places") and the event ends.
3. **Menu** (message 20): Set 1-5 with the five prices filled in, then View board and Quit. "Set n" is greyed out (`mbWinTopChoiceDisable`) when coins < its price or V < n. View board scrolls the map and opens the menu again.
4. **CPU choice:**
   - budget = coins;
   - if the Star is 10 spaces away or less (`mbMasuFind_TypeStepGet(space, 7)`), budget -= 20 to keep enough for the Star;
   - if budget > the 3-orb price, budget -= `rand(10)`;
   - it then picks the largest n (up to V and 5) with budget **strictly greater** than the price, or Quit if there is none (`mbComChoiceListDownSet`).
5. **Quit:** message 25 ("Don't forget about my glorious invention!"), and the event ends.
6. **Pay:** -price with the coin animation (`mbCoinAddDispExec`). The count is stored in work +0x12B0.
7. **Targets**, up to n spaces, filled in this order (each group shuffled):
   - (a) valid spaces with no orb on them (`mbCapMasuDispTypeGet` = 0);
   - (b) spaces holding another player's orb, which get overwritten;
   - (c) spaces holding the player's own orbs.

   So with enough empty spaces it never touches existing orbs. This is the same grouping as the Final Five launcher that the Boo-by-day patch copied.
8. **Orbs:**
   - `mbCapRandomListGet(list, 0x21)` copies **the board's orb list** (`lbl_802DA940`, `capsule.bin` entry 75 for boardNo 1) and the handler shuffles it.
   - Each launch then takes the next entry whose use mode (`mbCapUseModeGet`) is 1 (character orb) or 2 (trap), wrapping around.
   - From E. Gadd's list that means Goomba 11, Piranha Plant 12, Klepto 13, Kamek 16, Mr. Blizzard 17, Podoboo 20, Zap 21, Bob-omb 24, Paratroopa 25.
   - Each one is equally likely: the list's weights are ignored. Self-use orbs (Mushrooms, Bullet Bill, Flutter) are skipped.
   - Each placed orb is recorded with the **launching player as owner** (launch record at work +0x12B4: +4 player, +8 space).
9. **Launch:**
   - message 23 ("You want me to launch %d Orb? If you say so, youngin'!");
   - the cannon cutscene: wipe, camera on the cannon, sounds 0x5A8-0x5AC, rumble and camera shake;
   - one flying-orb process per orb (`fn_1_14F34`, `fn_1_1782C`), which lands each orb on its space (`mbCapAutoThrow` path).
   - Then message 24 ("Well, that's that! Stop on by anytime you want to set more!").

## Calamity Launcher rework (`src/tools/patches/apply_egadd_calamity_patch.py`, not run in Dolphin)
Changes the vanilla flow above in three places. Targeting, the orb pool and the cutscene are unchanged.

**Prices**
- **1-3 orbs free, 4 orbs 10 coins, 5 orbs 20 coins**, the same for every rank: every row of `lbl_1_data_C64` (w02Dll `.data`+0xC64) is now 0,0,0,10,20.
- The "not enough coins" exit no longer fires. Set 4/5 are greyed out below 10/20 coins.
- **No coin animation for a free launch:** the pay call `bl mbCoinAddDispExec` at `.text` 0x13EE4 goes through the DOL cave 0x802F8D70 (`cmpwi r4,0` / `beqlr` / `b mbCoinAddDispExec`), section 16, right after the wheel.

**CPUs always buy 3 orbs**
- `.text` 0x13DA0 (the first CPU-only instruction) is now `b 0x13E2C`.
- 0x13E2C-0x13E3C are now `li r3,2` / `cmpwi r26,3` / `bge +8` / `addi r3,r26,-1` / `nop`, followed by the original `bl mbComChoiceListDownSet`.
- With fewer than 3 free target spaces (r26) they take the largest option the menu enables. The old budget code (star distance, `rand(10)`) is skipped.

**Targets (vanilla, kept on purpose)**
- Order: empty valid spaces first, then spaces with **rivals' orbs**, then the launcher's own, each group shuffled. Trap spaces are never valid targets.
- A short-lived version merged the last two groups; the script now writes the vanilla words back at `.text` 0x14040 / 0x140FC.

**Menu** (bank 0x30 record 20, `messdata_eng.bin` only; `messdata.bin` is Japanese):
- "Launch up to 3 Orbs for free! / Any more than that will / cost you!"
- Set 1-3 "Free", Set 4/5 with the coin icon and x10/x20.
- The other languages keep the vanilla wording and show x0.

**Tested**
- Unicorn emulator: the cave (0 skips the call; -10/-20 tail-call with r3-r6 and LR intact) and the CPU snippet (V = 5, 4, 3 give Set 3; V = 2 gives Set 2; V = 1 gives Set 1).
- Byte diff: DOL 9 bytes in the cave; REL only the table, the 6 code words and the relocation target; only bank 0x30 record 20 in English.
- Re-runs and `apply_all.py --from egadd_wheel` change nothing.

**Unverified in Dolphin:** the menu layout with the new text; that a free launch plays no coin animation and the cutscene follows normally; that a CPU picks Set 3.

## Miracle space on the turntable (space 27, `src/tools/patches/apply_egadd_miracle_space_patch.py`, not run in Dolphin)
- **Space 27** (1, 811, -2399) changes from blue to **Miracle** (kind 4) in `w02.bin`/`w02n.bin`. It is the turntable space directly below the hub, on the path 28 -> 26 -> **27** -> 25.
  - Backups: `backups/w02*.bin.bak_before_egadd_miracle`.
- Space 26, the one first asked for, was left alone because it is Star spot 5. `fn_1_1572C` sets the spot the Star leaves to kind 1 (`li r4,1` at `.text` 0x15760), so a Miracle space there would turn blue after the first Star visit.
- The turntable already carries a Miracle space (58). Its code (`fn_1_4020`) only moves spaces and never rewrites their kind. The only other kind writer, `fn_1_71B4`, is the conveyor belts'.

## Shuffle-o-tron bonus orb (`src/tools/patches/apply_egadd_shuffle_patch.py`, not run in Dolphin)
**Vanilla** (day, spaces 36/38, `fn_1_B11C` -> step routine `fn_1_B570`):
- With n > 0 orbs: *Shuffle Orbs / Don't shuffle / View board*. CPUs always shuffle (`mbComChoiceLeftSet`).
- The machine takes **all** n orbs (mode 2, `mbPlayerCapsuleRemove` slot 0, n times). It then gives back n orbs (mode 3, count in r5), each drawn uniformly (`frand % count`) from the board's orb list (`mbCapListCopy`, 15 orbs), with "You got a %s Orb" (0x300005) for each.
- With 0 orbs: message 0x300008 "No Orbs, eh?" and nothing else.

**Now** n + 1 orbs come back while n < 3, otherwise n: 0 -> 1, 1 -> 2, 2 -> 3, 3 -> 3. Team mode (max 5) keeps 3+ unchanged, so the result never exceeds the limit.
- `.text` 0xB168 `bgt .L_B1A0` -> `b`: the offer appears with 0 orbs too. Mode 2's removal loop then runs 0 times and the machine animation plays as usual. Message 0x300008 is unused.
- `.text` 0xB2AC `mr r5,r28` (r28 = orbs on arrival) -> module-0 call to the DOL leaf **0x802F8D80**: `cmpwi r28,3` / `addi r5,r28,1` / `bltlr` / `mr r5,r28` / `blr`.
- Section 16 is now used up to 0x802F8D94 (0xC bytes left).
- Tested: the leaf in unicorn (n = 0..5 gives 1,2,3,3,4,5, r3/r4 kept). Byte diff: DOL 16 bytes in the leaf, REL the two sites plus one relocation. Re-runs and `apply_all.py --from egadd_wheel` change nothing.
- The Orb Morpher (night) is unchanged.

**Unverified in Dolphin:** the 0-orb run, i.e. the empty take-away animation, then one orb given.

## Orb Morpher rework (`src/tools/patches/apply_egadd_morpher_patch.py`, not run in Dolphin)
**Vanilla** (night, spaces 36/38, `fn_1_B334`): Transform / Nope / View board; CPUs always transform. It takes **all** the player's orbs (`fn_1_B570` mode 2) and pays their summed `mbCapSellCostGet` value (mode 4, "You get %d coin!"). With 0 orbs it shows message 0x30000D.

**Now** it still takes all the orbs, and the reward depends on how many went in (r26 = orbs held on arrival):
- 1 orb: every other player loses up to 7 coins (fewer if they have fewer) and the player gets the total.
- 2 orbs: the same, plus +1 Star with the game's popup.
- 3+ orbs (team mode can hold 5): each other player who has a Star loses 1, and the player gets them all. No coins.

**How**
- `.text` 0xB4F4 (`bl fn_1_B570`, mode 4, its only caller) -> module-0 call to **0x802F8DA0** in the new **DOL data section 17** (0x802F8DA0-0x802F9DA0; OSSetArenaLo clamp raised to 0x802F9DA0).
- It calls:
  - E. Gadd's show routine 0x802F87C0;
  - the spare change guy's steal loop pattern (`FN_COINS` / `FN_ADD_COINS`);
  - the Faire wheel's Star routine 0x80230220 (popup + wait).
- The machine motion and the closing line 0x30000B are unchanged.

**Text** (bank 0x30), reusing records that can no longer appear:

| Record | Was | Now (English in all languages) |
|---|---|---|
| 8 | Shuffle-o-tron "No Orbs" | "Whirr! The Orb Morpher drains / 7 coins from each of your rivals!" |
| 10 | the old "You get %d coin" | "And it spat out a Star / for you, too!" |
| 22 | Calamity "not enough coins" | "Whirr! Let's see which rivals / have a Star to spare!" |

- Record 9 (the offer) now reads "Feed it your Orbs to rob your rivals!", in English only.
- **Do not undo `egadd_shuffle` or `egadd_calamity` without moving these records.**

**Tested**
- Unicorn emulator with fake coins and Stars: 1/2/3/5 orbs, rivals with fewer than 7 coins, rivals with no Star, all rivals broke. Registers and stack checked.
- Byte diff: DOL = section header + clamp + new section; REL = one call site + relocation; messages = bank 0x30 only.
- Re-runs and `apply_all.py --from egadd_wheel` change nothing.

**Unverified in Dolphin:** the coin animations for three players in a row, the Star popups, and the new 4 KB section in memory.

## Robots (`src/tools/patches/apply_egadd_robots_patch.py`, not run in Dolphin)
Two cigar-smoking robots stand beside spaces 82 and 95. Walking past either one runs **the spare change guy's event**, unchanged for now:
- "Spare change?" Yes/No; pay 5 coins;
- then, at equal odds: an orb (**Mushroom / Super 'Shroom / Paratroopa (25)**, a third each; MP6 has no plain Koopa Troopa orb; Boo-away removed for the robots, `ORB_POOL` in the script, while Castaway keeps it), 20 coins back, asked again, nothing, or everyone else pays you up to 5;
- the user's lines, no speaker face.

The user plans to change the text and rewards later. The pay-5-coins idea stays.

**Nodes** (Castaway space 100's design). In `w02.bin`/`w02n.bin`, appended spaces with kind 0, type 0, flag **0x400000** and one link:
- **114** at (-1026.5, 1164, -5054), between 82 and 83 (top pipe row); 82 now links to 114.
- **115** at (-3344, 568.5, -1286.5), between 95 and 113 (round platform by the crane); 95 now links to 115.
- Kind 0 costs no step and cannot end a move, so the event fires only when walking past.
- Backups: `backups/w02*.bin.bak_before_egadd_robots`.

**Cards**
- `hsf_build.build_card`, 156 x 312 (the tax man's size), file **58** of both archives (`0xE5003A` / `0xE6003A`). Two models are made from it.
- Positions `ROBOT_POS`: beside the trigger nodes, i.e. halfway between the two spaces, set off the path.
  - (-1026.5, 1164, -5210): 156 behind node 114.
  - (-3494, 568.5, -1286.5): 150 left of node 115.
  - The first version stood beside spaces 82 (-1199, 1159, -5210) and 95 (-3470, 566, -1079). In Dolphin (2026-11-06) both robots showed and were cut out cleanly, but they were not between the spaces, so they were moved.
- Art: `cut_out()` in the script flood-fills the white background, the sticker border and its shadow from the edges (min channel >= 130, saturation <= 30), drops opaque islands under 400 px, and crops. The result is `src/tools/assets/egadd_robot.png`. It is rebuilt when `robot.jpeg` is newer.

**Hooks** (chained onto the wheel's):
- `.text` 0x3A0C -> `0x802F9080`: calls the wheel's pass cave 0x802F8800 with r3/r4, then runs the event on flag 0x400000.
- `.text` 0x1B44 -> `0x802F90E0`: calls the wheel's init cave 0x802F8D00, then creates the two cards.

**Code**
- In section 17: show 0x802F8FA0, ask 0x802F8FE0, pass 0x802F9080, init 0x802F90E0, event 0x802F91E0, data 0x802F9460 (robot A position, hold floats, orb pool, then robot B position). It ends at 0x802F94A0.
- Built with `apply_castaway_spare_change_patch`'s builders, now parameterised. The Castaway output is byte-identical.

**Text:** bank 0x30 records 34-42, the spare change guy's 9 lines, English in every language file.

**Re-runs**
- `egadd_wheel` keeps the robots' relocations and records 34-42.
- `egadd_calamity` and `egadd_morpher` keep records 34-42.
- Every E. Gadd step re-run alone, and `apply_all.py --from egadd_wheel`, change nothing. One relocation per hook site.

**Tested** (unicorn emulator, stubbed game calls):
- the pass cave (wheel first with the original r3/r4; event only on flag 0x400000; registers and stack intact);
- the event (bank 0x30 ids 0x300022...: refusal, and the pay plus everyone-pays outcome);
- init by day and by night (wheel first, two cards `0xE5/0xE6003A` at the two positions).

**Seen in Dolphin (2026-11-06, first positions):** both robot cards visible, facing the camera, cleanly cut out, a sensible size.

**Unverified in Dolphin:** the moved positions, the event itself, that walking past costs no step, and that the wheel on space 7 is unaffected.
