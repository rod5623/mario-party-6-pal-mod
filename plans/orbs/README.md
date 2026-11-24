# Orbs: customizing existing orbs and adding new ones (GP6P01)

Status: research only. Nothing here has been implemented or tested in Dolphin. Findings come from disassembly and data dumps of the Europe build.

## Caveat on names and addresses
- `src/config/GP6P01/symbols.txt` has only `fn_XXXXXXXX` / `lbl_XXXXXXXX` names. Orb names (`mbCapUse`, `capsuleData`, ...) come from the GP6E01 symbol file (`config/GP6E01/symbols.txt` lines 4330-4339, 5188-5530, 10077-10161; splits in `splits.txt` lines 1285-1340) and were mapped to P01 by matching function/object sizes, then checked by decoding the data.
- The shift is not constant: `mbPlayerCapsule*` is at -0x5D0, the `Cap*` events at -0x4A4, data tables at +0x1D730. Always use the P01 addresses below.
- Disassembly: `build/GP6P01/asm/auto_03_800EF6C8_text.s` (text), `auto_07_80259D80_data.s` (data; `lbl_80266BDC` at line 14254, `lbl_80268500` at 16243, `lbl_8026753C` at 14858, `lbl_80267D20` at 15656).
- Field meanings marked "inferred" come from accessor names plus the code read, not from tracing every consumer.

## Where things live
- **Main DOL:** all orb logic and data (inventory, tables, `mbev_Cap*` handlers, selection, throw/trap, AI, Orb Hut `ev_Shop` at `0x801EA00C`, orb space `mbCapMasuExec` at `0x8019A18C`).
- **RELs:** only board overlays call the inventory API (relocations to `fn_8015D6FC`, `fn_8015D8A4`, `fn_8015DD58`, `fn_8015DFF0`): `w02Dll`, `w04Dll`, `w05Dll`, `w06Dll`, `w10Dll`. No REL holds orb data.
- **Disc data:** `files/data/capsule.bin` (DATADIR index 20), `capsulechar0-4.bin` (21-25), `capsulemesj.bin` (26), `capsuleshop.bin` (27). Note `include/datadir_table.h` is the E01 list; P01 indices are the sorted order of `files/data`. In an id like `0x0014xxxx`, 0x14 = `capsule.bin`.
- **Messages:** `files/mess/messdata*.bin` (see Messages).

## Orb IDs
ID is a signed byte. Valid IDs are 0-52 (check is `id < 0x35`); tables have 60 slots. The enum is not in any header; names are the DOL debug strings plus English text from banks 55/56. "Cat" is the field at +0x10.

| ID | Debug name | English | Cost | Cat |
|---|---|---|---|---|
| 0 | KINOKO | Mushroom | 5 | 0 |
| 1 | S KINOKO | Super 'Shroom | 10 | 0 |
| 2 | P KINOKO | Sluggish 'Shroom | 10 | 0 |
| 3 | M KINOKO | Metal Mushroom | 20 | 0 |
| 4 | KILLER | Bullet Bill | 20 | 0 |
| 5 | DOKAN | Warp Pipe | 15 | 0 |
| 6 | HANACHAN | Flutter | 30 | 0 |
| 7 | N KINOKO | Cursed Mushroom | 30 | 0 |
| 8, 9 | NULL, NASI | unused | | |
| 10 | TOGEZO | Spiny | 10 | 1 |
| 11 | KURIBO | Goomba | 15 | 1 |
| 12 | PAKKUN | Piranha Plant | 20 | 1 |
| 13 | JANGO | Klepto | 5 | 1 |
| 14 | HANUKE | unused | | |
| 15 | KOKAMEKKU | Toady | 10 | 1 |
| 16 | KAMEKKU | Kamek | 5 | 1 |
| 17 | THROWMAN | Mr. Blizzard | 10 | 1 |
| 18, 19 | SUKA, KARA | unused | | |
| 20 | BOBLE | Podoboo | 10 | 2 |
| 21 | BIRIQ | Zap | 15 | 2 |
| 22 | TUMUJIKUN | Tweester | 15 | 2 |
| 23 | DOSSUN | Thwomp | 15 | 2 |
| 24 | BOMUHEI | Bob-omb | 10 | 2 |
| 25 | PATAPATA | Paratroopa | 10 | 2 |
| 26-29 | NETA, GA, TUKI, TA | unused | | |
| 30 | HONE | Snack | 20 | 3 |
| 31 | LIGHT | Boo-away | 10 | 3 |
| 32 | TARU | Barrel | 15 | 3 |
| 33-39 | | unused | | |
| 40 | KILLER MOVE | Bullet Bill Move | | |
| 41 | KETTOU | Duel | | |
| 42 | MIRACLE | Action / Miracle | | |
| 43 | KOOPA | Bowser | | |
| 44 | DONKEY | DK | | |
| 45 | VS | Vs. | | |
| 46 | R_TERESA | Boo space | | |
| 47 | DICE | Dice Block | | |
| 48 | YAMERU | "Call it quits" | | |
| 49 | | unused | | |
| 50-52 | DEBUG CAM / WARP / SETPOS | debug orbs | | |
| 53-59 | | unused (fail `< 0x35` checks) | | |

Notes:
- **Special spaces are orbs.** IDs 40-46 are hidden orbs (cost 1, cat 9/10, listFlag 0). The existing Bowser and DK patches edit handlers of orbs 43/44: `fn_801BE24C` (`ev_CapKoopaStart`), `fn_801BBDC0` (`ev_CapDonkeyStart`).
- IDs 47 and 48 are special-cased in `mbCapUse` at `0x801BFE1C` / `0x801BFE70`.
- Message-bank indices are not IDs: gaps are closed in the banks (ID 15 = message 13, ID 25 = message 12).

## Data tables (P01)

### capsuleData: `lbl_80266BDC`, 60 x 0x28 bytes (row = `0x80266BDC + id*0x28`)
| Off | Meaning | Evidence |
|---|---|---|
| +0x00 | model file id `(0x14<<16)\|n` into `capsule.bin` | `mbCapFileGet` 0x801CA4D4, `mbCapValidCheck` 0x801CA6C0 |
| +0x04 | frame/overlay model id (0x14001C-0x14001F per category, 0x140020 Miracle) | `mbCapObjColorCreate` |
| +0x08 | description message id (bank 55 / 0x37) | `mbCapDescMesGet` 0x801CA52C |
| +0x0C | name message id (bank 56 / 0x38) | `mbCapUseMesGet` 0x801CA564 |
| +0x10 | placement category (0 self, 1 hit, 2 trap, 3 defensive, 9/10 special) | `mbCapMasuPatGet` 0x801CA5D4 |
| +0x14 | colour index 0-3 (inferred; feeds trail colour) | `mbCapColorGet` 0x801CA60C |
| +0x18 | base price | `mbCapCostGet` 0x801C9244 |
| +0x1C | rarity class byte 'A'-'E'; 'Z' = never drawn (inferred) | `mbCapNextGet` 0x801CAA78 |
| +0x1E | use mode u16: 0 self, 1 throw/place, 2 trap, 3 cannot use | `mbCapUseCheck` 0x801CA64C, `mbCapUseModeGet` 0x801C8EDC |
| +0x20 | pointer to debug name string | |
| +0x24 | list flag byte | `mbCapListExcludeCheck` 0x801C927C |

Unused rows have file id 0, so `mbCapValidCheck` rejects them (pattern `00 38 00 22`).

### Event dispatch: `lbl_80268500`, 60 x 0x1C bytes (0x708)
| Off | Meaning |
|---|---|
| +0x00 | event process entry `mbev_Cap<Name>` |
| +0x04 | kill function |
| +0x08 | optional callback, only trap orbs 20-24 (inferred) |
| +0x0C | UI mode 0/1/2 (switch at 0x801D4A0C) |
| +0x10 | camera/pre-mode 0/1/2 |
| +0x14 | character data file: `0x150000` capsulechar0, `0x160000` char1 (Bowser, DK), `0x170000` char2 (placed-orb characters), `0x190000` char4 (Duel, Miracle), `0xFFFFFFFF` none |
| +0x18 | flag = 1 for trap orbs 20-24 |

Orbs 30, 31, 32, 45 use `mbev_CapNull`; 50-52 use debug handlers.

Handler addresses:
- Mushroom `fn_8019B050`, Super `fn_8019B5A0`, Sluggish `fn_8019BAF0`, Metal `fn_8019C040`, Bullet Bill `fn_8019C56C`, Warp Pipe `fn_8019C620`, Flutter `fn_8019D494`, Cursed `fn_8019EED4`
- Spiny `fn_801A1FB8`, Goomba `fn_801A3190`, Piranha `fn_801A3BC8`, Klepto `fn_801A4A74`, Paratroopa `fn_801A5674`, Toady `fn_801A714C`, Kamek `fn_801A8CBC`, Mr. Blizzard `fn_801AA42C`
- Podoboo `fn_801AAC68`, Zap `fn_801AC48C`, Tweester `fn_801ADFB4`, Thwomp `fn_801AF340`, Bob-omb `fn_801AFE34`
- Boo `fn_801B16A8`, Miracle `fn_801B4504`, Duel `fn_801B920C`, DK `fn_801BBB7C`, Bowser `fn_801BE08C`

Dispatch path: `mbCapUse` (0x801BFDEC) -> `mbev_CapCall` (0x801D44B8; also called from space code `mbev_MasuMove+0xE0`, `mbev_MasuCapStop+0x348`) -> function at 0x801D5EB4, which copies a 0xBF4-byte parameter block, finds a free slot in `lbl_802DC2E0` (8 slots) and starts the process from the table row.

### Shop and drop lists
- `lbl_80267D20` (0x60 bytes): 12 pairs `(boardNo, fileId)`, boardNo from `GW_SYSTEM+8 & 0x1F`; boards 0-10 map to `capsule.bin` entries 74-84 (`0x14004A`-`0x140054`); -1 ends.
- `mbCapListRead` (0x801C7EDC) copies the board's list into `lbl_802DA940` (33 entries x 16 bytes, id -1 terminates).
- Entry (16 bytes, decoded from `capsule.bin` entries 74-84): byte 0 orb ID; bytes 1-3 price by rank bucket (0 = use `capsuleData +0x18`); bytes 4-7 orb-space weights for the first half of the game, bytes 8-11 orb-space weights for the second half, bytes 12-15 Orb Hut weights. Each weight group has 4 values, one per player rank (`GW_PLAYER+9` bits 4-5, 0-3). In the vanilla lists each group/rank sums to 100. A weight of 0 means the orb is not offered to that rank in that context. The 'first/second half' split is inferred from a comparison against half the turn limit in `mbCapMasuNextGet`.
- Lists: boards 0-5 have 10-15 orbs; boards 6-8 only orbs 2 and 7 (weight 50); boards 9-10 only orbs 0, 10, 23.
- `capsule.bin` has 85 entries: container = count, absolute offsets, then each entry `u32 size, u32 type (7 = zlib), u32 size, u32 csize, zlib`. Entries 0-37 orb HSF models, 38-57 sprite banks, 58-73 effect HSFs, 74-84 board lists. `mbev_CapInit` (0x801D5A30) preloads 0x35, 0x38, 0x31, 0x37.
- Shop: `mbCapShopListGet` (0x801CBC68), called from `ev_Shop+0x138`; returns up to 3 orbs; cost lookups at `ev_Shop+0x174`, `+0x1F4`, `+0xE88`.

### Orb Hut selection (`mbCapShopListGet` 0x801CBC68, `CapShopNextGet` 0x801CB5A4)
- Always at most 3 orbs: it calls `CapShopNextGet` three times, each excluding the orbs already chosen, so the three are distinct. If fewer than 3 are eligible the shop shows fewer.
- Eligible = board-list entries whose shop weight (bytes 12-15, by the player's rank) is above 0. Selection is a weighted roll: the candidates are shuffled and sorted by that weight, then a random number scaled by the total of the orb-space weights (bytes 4-7) is walked down the list; if it overshoots, the first (lowest-weight) candidate is used, so a slot is never empty from this.
- The held-orb halving in this routine is applied to the orb-space weight group (bytes 4-7), not the shop group it rolls on, so holding an orb probably does not reduce its shop odds (looks like a quirk of the original code; inferred).
- Prices come from bytes 1-3 (by rank bucket) or fall back to `capsuleData +0x18` when the byte is 0 (`mbCapBuyCostGet` 0x801C8F98).

### Orb-space draw (corrected)
- `mbCapMasuExec` (0x8019A18C) runs when a player lands on an orb space (skipped when the current turn has reached the turn limit). It picks the orb with `mbCapMasuNextGet` (0x801CAEE4), which draws from the **board list** (`lbl_802DA940`): candidates are entries whose weight for the player's rank is above 0 (groups at +4 / +8 as described above), a held orb's weight is halved, the list is shuffled and sorted by weight, and one orb is picked by a weighted roll over the weight total. If the player already holds the maximum (3 orbs, 5 in team mode) the game asks which to replace or discard before adding.
- The class-based chance table `lbl_80268164` (A-E classes, 3 tiers x 4 ranks) and `mbCapNextGet` (0x801CAA78) are **not** used by orb spaces. `mbCapNextGet` has no direct callers in the DOL (only a one-instruction wrapper `fn_80214CD4`, and `fn_80214CD8` wraps `mbCapMasuNextGet`); it draws from every valid `capsuleData` row with ID 0-32 by class instead of the board list, so the `capsuleData +0x1C` class byte only matters for that routine. Who calls the wrappers (if anything) was not found.
- Last Five scatters orbs on spaces through a separate random-list routine (`fn_801CBE14`); not traced.

### AI
- `mbCapComChanceGet` (0x801C938C), `mbCapSelectComGet` (0x801C9BB8), `CapSelectMasuCom` (0x801C5BE8), `CapCheckComPath` (0x801C98A8), `CapSelectComGet` (0x8019A020).
- `lbl_8026753C`: 23 records x 0x2E bytes: `s16 id`, then 11 character slots of `(s16 chance, u8 condition, pad)`; last id -1. Rows exist for IDs 0-6, 10-13, 15-17, 20-25, 30, 31; others return -1. Slot index = charNo capped at 10. Conditions 0x20/0x2A/0x61/0x62.
- Jump table `lbl_802680B0` covers IDs 0-31 only (`cmplwi r20,0x1f; bgt`).
- `lbl_80268130` (10,11,12,13,25,15,16,17) and `lbl_80268150` (20-24) are random-orb scatter sets, not AI tables (corrected after a later check: `fn_801CA164` indexes the first as `(id-10) mod 8`, `fn_801CA26C` the second as `(id-20) mod 5`). A new orb outside IDs 10-17 / 20-24 is never scattered.
- Dispatch row `+0x08` is the trap's effect callback (run when a victim steps on the trap); `+0x00` is only the visual animation. Placing an orb on the board also requires it to be in the board list (`lbl_802DA940`); a rarity byte alone does not make it obtainable.
- Visual tables by category/colour: borders `0x140018`-`0x14001B` (0x802682D8), highlights `0x140031`-`0x140033` (0x802682F0), `ev_CapEffRingFile` (0x80268C98), trail colours 0x80268344, throw colours 0x802679A4.

## Player data and placed orbs
- `GW_PLAYER` (`include/game/gamework.h`), array `lbl_80282E70`, stride 0x108. `s8 capsule[3]` at +0x05..+0x07 (-1 = empty); `s16 capsuleUse` +0x12 (selected slot); `s8 capsuleMasuNum` +0x16 (placed count, cap 99 at 0x801D47B0); `s16 capsuleUseNum` +0x34.
- `GW_SYSTEM` is `lbl_80283290`, size 0x2C0.
- `mbPlayerCapsuleMaxGet` (0x8015D6B8): 3 normally, 5 in team mode (`tagF` = bit 6 of `GW_SYSTEM+0`); team slots 3,4 map to the teammate's `capsule[0..1]`.
- Accessors: use set/get 0x8015D664/0x8015D690; add 0x8015D6FC; remove 0x8015D8A4; find 0x8015DCBC; get slot 0x8015DD58; team get 0x8015DE6C; count 0x8015DFF0; team count 0x8015E128.
- Callers of Add: orb spaces (`mbCapMasuExec+0x2D8`, `+0x390`), `mbev_CapKokamekku` (Toady steal), `ev_Shop`, Bowser Mini-Game (`ev_SingleKoopaMg+0xC44`), Last Five (`ev_Last5CapsuleAdd5` 0x802026F8 via `mbCapRandomListGet`).
- Callers of Remove: Bowser Mini-Game, `ev_CapKoopaCoin`, Boo and Mr. Blizzard handlers, throw-away menu, shop swap.
- Placed orbs: `GW_SYSTEM.masuCapsule[256]` (s16, +0x3E, indexed by space id), value `id | owner<<8`. `mbMasuCapsuleReset` 0x801772D0, `Get` 0x80177310, `Set` 0x80177334. Accessors 0x801C8D54 (type), 0x801C8D9C/0x801C8DAC (owner), 0x801C8DDC/0x801C8E3C (setters); `mbCapMasuCapsuleSet` (0x801CA380) skips IDs 30 and 43 on placement. Runtime space struct (0x70 bytes) holds a copy at +0x32. Shared event globals at `0x802DD758`-`0x802DD774`.
- Orbs persist in `GW_PLAYER` / `GW_SYSTEM` (mid-game save only).

## UI and visuals
- `mbCapObjCreate` (0x801CC5D0): HSF model from `capsule.bin` plus a frame model per category; pool of 8 objects; special-cases ID 0x30. `mbCapObjColorCreate` (0x801CCBC4): up to 0x80 colour objects.
- Menus: `mbCapUse` 0x801BFDEC, `CapUse` 0x801C0040, `CapUseSelect` 0x801C00DC, throw-away `CapUseDelete` 0x801C782C / `CapUseDeleteWin` 0x801C78D4, description window `mbCapDescWinCreate` 0x801CC3BC, HUD `mbStatusCapsuleDispSet` 0x8018D2B8 / `mbStatusCapsuleFocusSet` 0x8018D33C.
- Throw / place: `CapPlayerThrow` 0x801C165C, `mbCapAutoThrow` 0x801C4304, `mbCapSelectMasu` 0x801C4B3C, `CapSelectMasuPlayer` 0x801C4D2C, trap trigger `mbev_CapCallTrap` 0x801D4B7C.
- Shop: `ev_Shop` 0x801EA00C, `ev_ShopSelect` 0x801EB700, pedestal tables ~0x80268DF8.

## Messages
- Files: `files/mess/messdata_eng.bin`, plus `messdata.bin`, `_fra`, `_ger`, `_ita`, `_spa`. All have 75 banks and identical orb-bank counts, so one edit pattern applies to all six.
- Structure: `u32 bankCount`, `u32 bankOffset[]` (relative to file +4); each bank `u32 recordCount`, `u32 recordOffset[]` (relative to bank base +4), 4-byte-padded records. Message id = `(bank<<16)|index`. Reference code: `build_messages` in `tools/patches/apply_dk_bonus_patch.py` (lines 228-281), `patch_message` in `tools/patches/apply_bowser_bonus_patch.py` (line 130).
- Record header `00 15 00 03` dialog / `00 07 00 01` names. Codes: 0x10 space, 0x0A newline, 0xC2 `!`, 0xC3 `?`, 0x82 `,`, 0x85 `.`, 0x5C `'`, `=` for `-`, `1E nn` colour, `1F nn` parameter, `FF 00` page end. Plain ASCII commas written by the existing scripts may not be the same glyph as 0x82; not confirmed in game.
- Banks: 53 CAPSULE_EX01 (8), 54 CAPSULE_EX02 (21), **55 CAPSULE_EX99** (59 records: 0-35 per-orb descriptions, 36+ UI strings), **56 CAPSULE_EX98** (37 records: 0-34 names, 35-36 event messages), 57 SHOP_EVENT (30), 58 CAPSULE_MASU (5), 59-63 TERESA/MIRACLE/KETTOU/DONKEY/KOOPA_MASU.
- The UI strings after the first 35/36 records are probably hardcoded by index, so append new records (bank 55 from index 59, bank 56 from index 37) and point `capsuleData +0x08/+0x0C` at them.

## Customizing existing orbs (easy: data edits)
| Change | Target |
|---|---|
| Price | `capsuleData +0x18`; board-list price bytes in `capsule.bin` entries 74-84 |
| Rarity from orb spaces | `capsuleData +0x1C` class byte; weights in `lbl_80268164` |
| Shop availability and weight | board lists in `capsule.bin` 74-84 (needs repack), or patch `mbCapListRead` |
| Name / description | banks 56 / 55, all six language files |
| Use mode / category | `capsuleData +0x10`, `+0x1E` |
| AI willingness | `lbl_8026753C` (IDs 0-31 only) |
| Behaviour (e.g. Mushroom gives more dice) | edit the handler (table above) with a code-cave hook, as in the DK and Bowser patches |

Suggested first target: a pure data patch (e.g. change prices and the Mushroom rarity), applied through a `tools/apply_orb_data_patch.py` that patches both the DOL and `auto_07_80259D80_data.s`.

## Adding new orbs
Per new orb:
1. Pick a free ID below 53: 8, 9, 14, 18, 19, 26-29, 33-39, 49.
2. Fill a `capsuleData` row. Reuse an existing `capsule.bin` model (entries 0-37) and a frame `0x14001C`-`0x14001F`. The row must have a non-zero file id to pass `mbCapValidCheck`.
3. Fill a dispatch row in `lbl_80268500`: reuse a vanilla handler or point at a hand-assembled handler in a code cave. Choose a character-data file from the list above or `0xFFFFFFFF`.
4. Make it obtainable: a board-list entry in `capsule.bin` 74-84, and/or its rarity class for orb spaces.
5. Append name and description records to banks 56 and 55 in all six language files.
6. Optionally add AI records. IDs above 31 are skipped by the AI jump table, so a new orb in the free range 33-39 would need that jump table extended; IDs in 8, 9, 14, 18, 19, 26-29 are covered.
7. IDs 53-59 need the constants changed at 0x801CA6E0 (`mbCapValidCheck`), 0x801CAAC4 (`mbCapNextGet`) and 0x801C9BB8 (`mbCapSelectComGet`; only the first two were confirmed).

Easiest new orb: a re-skinned clone of an existing one (new ID, same handler, new price/name). Next: a clone with a small handler tweak. Hardest: a genuinely new effect plus a new model.

## Hard limits
- 60-entry tables sized exactly (0x960 and 0x708 bytes); ID validity `< 53`.
- AI jump table IDs 0-31; AI chance table 22 rows.
- List buffer 33 entries; shop shows 3; inventory 3 (5 in team mode); 8 simultaneous event processes; 8 pooled orb objects; 256 placed-orb spaces; placed value is `id | owner<<8`; `GW_PLAYER.capsule` is s8.
- Category 0-3 effect tables (borders, rings, trails) have 4 entries, so new orbs should reuse a category.
- A handler that needs a character model must use `capsulechar0-4.bin` or `0xFFFFFFFF`.
- New models require repacking the zlib-compressed `capsule.bin`.

## Patch technique (from `tools/apply_*.py`)
- Each script patches the built DOL (`build/GP6P01/main.dol`, via `dol_offset`) and the generated asm (`build/GP6P01/asm/auto_00_80003100_init.s`, `auto_03_800EF6C8_text.s`, `auto_07_80259D80_data.s`, `auto_09_802DCE00_sdata.s`) so Ninja rebuilds stay in sync. Scripts check original bytes and are idempotent.
- Helpers in `apply_bowser_bonus_patch.py`: `encode_branch`, `patch_dol_instruction`, `patch_asm_instruction`, `patch_asm_word`, `patch_word_table`, `replace_bytes`, `patch_message`. Mini-assembler: `assemble()` in `apply_dk_bonus_patch.py` lines 113-145.
- Hooks are `b`/`bl` to a hand-assembled cave in `.init` (e.g. 0x801BC6D0 -> 0x800036E8).
- Caves already used: 0x80003614-0x8000363C, 0x80003628/0x80003670/0x800036A0 (Bowser fix), 0x800036E8-0x80003748 and 0x80003750-0x800037E4 (DK). Leave 0x80003748 (an unrelated `blr`) alone.
- Free zero runs: 0x80003830 (0xB4), 0x80003918-0x80003E18 (0xCC each), 0x80003F18 (0x2CC), 0x80004A18 (0x1CC), 0x80004D18 (0x4CC) up to 0x80005418. These lie inside the TRK interrupt-vector table (0x800035E4-0x80005518); nobody has proved they are unused at runtime beyond the Dolphin tests listed in the main README, which still need retesting.
- Larger code would need a new DOL section (header has 5 unused text slots and 3 unused data slots). Nothing in the repo does this yet, and whether the heap stays above a section placed past the current bss end is untested.
- No script modifies `capsule.bin`; a repack tool (parse, inflate, edit, re-deflate, rebuild offset table) would have to be written.

## Risks and open questions
- Cave space is limited and unverified at runtime; a big new handler may exceed it.
- The weight groups at list-entry +7 and +10, and the rarity tier selection, were not traced.
- Which of the three `< 0x35` checks matter for IDs 53+ is only partly confirmed.
- Packaging: the main README notes the rebuilt DOL is 32 bytes smaller than the original and ordinary mods are untested, so the whole pipeline needs a Dolphin smoke test first.
- Other language files must get the same message appends or non-English players will see wrong text.

## Roadmap
1. Data-only patch: prices, rarity weights, names (all six languages).
2. Edit one vanilla handler (small behaviour change) via a cave hook.
3. Add a clone orb in a free ID (new row, new text, shop entry via a `mbCapListRead` patch or a `capsule.bin` repack tool).
4. Add an orb with a custom handler.
5. Extend limits (IDs 53+, AI jump table) only if needed.

## Dolphin test checklist
- Orb Hut lists and prices the changed or new orb; buying works for each rank.
- Orb space can award it; it appears in the inventory HUD with the right name and description.
- Use it: self, throw and trap variants; it triggers, animates and its kill function cleans up.
- Team mode with 5 slots; the throw-away menu; AI use; a mid-game save and load.
- Check all six languages for text.
