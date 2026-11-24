# Duel ports of Daft Rafts (m609) and Lift Leapers (m618): findings

Written for: you, as a research note. Nothing here has been run in Dolphin. Offsets are REL `.text` offsets; "inferred" items are unverified.

Names to overlays: Daft Rafts = m609, Lift Leapers = m618 (from message order in `mg_name.h`).

Shared facts
- Neither REL has any `GwSystem`/`MgDataTbl` type check, so every hook must test `MgDataTbl[GwSystem.mgNo].type == 6` itself (type-3 pattern in `apply_whatgoesup_battle_patch.py`, with 6). Neither is type-aware, so a 4P entry stays unchanged.
- Duelists: `fn_801B920C` sets all `grpNo` to 2, then the two duelists to 0 and 1. Test `GwPlayerConf[i]+6 < 2`. Both RELs index players by player index (no remapping), so slots stay put.
- Both are fixed `for i<4` everywhere. "Don't spawn" would leave null pointers in many unrolled accesses. Rejected for both.
- Approach: second table entry (type 6, same overlay) plus module-0 relocation hooks into DOL caves, as in `battle_port.py`.

## Daft Rafts (m609)
- Per-slot struct `bss_24C`, stride 0x130, built from `GwPlayerConf` by `fn_1_3C0` (call at 0xD27C). Spawn loop in `fn_1_D1CC` 0xDBA0-0xDDA0. One shared camera, so no split-screen problem.
- End condition `fn_1_4FC0` (0x4FC0-0x52B4): per slot, `+0x1B` = 1 finished, -1 out (set when `+0x6D != 0`). The game ends only when finished + out == 4. So 2 unresolved slots would hang the game.
- Winner reporting `fn_1_111A8`: every slot with `+0x1B >= 0` is a winner (`GwPlayer+0x28 = 10` at 0x112BC, `fn_80072388` at 0x112F8). No `+0x2C`, no type checks.
- Options
  - A. Do not spawn slots 2/3: high risk (`fn_1_2780`, `fn_1_52B8` etc. deref the model handles unconditionally). Not recommended.
  - B (recommended). Spawn all four, retire the extras with the game's own elimination state: after `fn_1_3C0`, set `slot[i]+0x6D = 1` for non-duelists. `fn_1_52B8` (0x53A4) already hides the model and `fn_1_4FC0` counts the slot as out, so the race ends once both duelists resolve. Hook: relocation at the `bl fn_1_3C0` (0xD27C), cave calls it (target = LR - 0xCEC0), then loops i=0..3.
  - C (fallback). Also re-assert `+0x1B = -1`, `+0x72 = -1` for extras each frame by hooking the `bl fn_1_4FC0` at 0x4FAC.
- Open points: both duelists finishing gives two winners, which `fn_801BB0D0` reads as a draw (finish order not decoded: `bss_30+0x130/+0x140`); meaning of `+0x6D == 1` is inferred, so extras may splash on frame 1; finding `bss_24C` at runtime inside a cave; the `.text` file offset for m609.
- Effort: low to medium. Good first target.

## Lift Leapers (m618)
- 4 cameras (`li r3,0xf` at 0x158; bits 1,2,4,8). Quadrants set only in `fn_1_796C` via `fn_80027AF4/800279D4/80027A54`; cross point = (320 ± 5.3333·s, 240 ± 4·s) from rodata `19C/1A0/1A4/1A8`. P0 top-left, P1 top-right, P2 bottom-left, P3 bottom-right. Each player's model carries its own camera bit; the world uses 0xF.
- Players: `fn_1_1CE0` (bound `cmpwi r31,4` at 0x2100). Per-player AI/state loop `fn_1_214C` (body 0x2184-0x319C, increment at 0x31A0). `conf+8` is the CPU flag.
- Finish: inside `fn_1_214C`, 0x2790-0x28C8, a player is added to a finisher list at 0x28BC-0x28C8; winner chosen at 0x31AC-0x31E0 (random tie-break), `bss_54C` set. So the game does NOT wait for all four; the first finisher of any slot ends it. `fn_1_910` then calls `fn_80072388` (0x9B0) and writes `+0x28 = 10` (0x9E8).
- Options for the extra two players
  - A. Don't spawn: high effort, many null derefs (`fn_1_84C/910/DA8` unrolled, `fn_1_1B40`, `fn_1_644`, `fn_1_4BE0`), the all-four wait at 0x17E8-0x188C. Not recommended.
  - B. Spawn but filter finishing: skip the finisher add at 0x28BC-0x28C8 for non-duelists. Low effort; extras still move and show.
  - C (recommended, with B's effect). Freeze them: hook the loop top at 0x2184 and for non-duelists jump to 0x31A0 (LR-relative skip). No AI, no finish test. Hide them by changing `li r3,0xf` at 0x158 to `0x3`, which also drops cameras 2/3. If a human's slot still moves via the object's own input path, hide with `fn_80087994(obj,1)`.
- Layout for 2 players
  - Minimal: keep the quadrant layout with two empty quadrants (cameras 0 and 1 only), zero code beyond the camera mask.
  - Better: left/right halves by patching rodata `1A4` 240→480 and `1A8` 4→0 and aspect `1B8` 1.2→about 0.67 (inferred, arithmetic only; not run). Per-player messages (ids 0x6D5-0x6D8, `fn_80040070`, `fn_8005C954`) may sit oddly; unchecked.
- Risks: the random "special" slot value 0x38 (`fn_8003FD50(4)` at 0x2118) may land on a non-duelist (effect unknown); the draw/timeout path wait (0x17E8-0x188C) needs all four slots idle with input, so frozen extras may hang it (second hook needed); human input on frozen objects not traced.
- Effort: medium.

## Table/infrastructure (same as Battle ports)
New type-6 entries need table growth entries (relocated table has room to index 96), `instDll` clamp already 0x60, Battle-style thumbnails do not apply to Duel (duel choice screen tables unexamined), and `MgNoGet(ovl)` returns the first match so practice/pause text sees the 4P entry.

## Recommended order and verification
1. Daft Rafts duel (option B) as the prototype.
2. Lift Leapers duel with the freeze hook (option C) + camera mask; then optionally half-screen layout.
3. Dolphin tests: 4P entry still plays unchanged for both; Duel space offers the game; only duelists appear; the race/lift ends when a duelist finishes; non-duelist humans cannot affect it; draw/timeout path does not hang; result screen shows the right duelist winning.

## Implemented (not yet tested in Dolphin)
Run after `apply_mgtable_move_patch.py` and `apply_battle_ports_patch.py`; both scripts are safe to re-run. Deployed to `root` (Start.dol, `dll/m609dll.rel`, `dll/m618dll.rel`).

| Script | Table entry | Hook | Behaviour |
|---|---|---|---|
| `tools/patches/apply_daft_rafts_duel_patch.py` | 86 (copy of m609, type 6) | `bl fn_1_3C0` at .text 0xD27C -> cave `0x802F7AA0` | Calls `fn_1_3C0`, then for a type-6 entry sets slot `+0x6D = 1` (dead) on every slot with `grpNo >= 2`. The game hides that raft and counts it as out, so the race ends on the two duelists. |
| `tools/patches/apply_lift_leapers_duel_patch.py` | 87 (copy of m618, type 6) | `mulli r4,r31,0x68` at 0x2184 (fn_1_214C loop top) -> cave `0x802F7BA0` | For a type-6 entry and `grpNo >= 2`, jumps to the loop increment at 0x31A0, so non-duelists are never updated and can never finish or win. |

Changes to shared helpers: `emit_type_check` and `add_table_entry` take an optional type (default 3).

Decisions and limits
- Lift Leapers keeps all four quadrants: the duelists can be any two of the four player slots, so switching cameras off by slot (the `li r3,0xf` at 0x158) would hide a duelist. The two non-duelist quadrants just show a stationary player. A real 2-viewport layout is still open.
- Daft Rafts: if both duelists reach the end, both get `+0x28 = 10`, which the Duel result reads as a draw (finish order is not recorded by the game).
- Lift Leapers: the post-game "all four" wait at 0x17E8-0x188C and the random special-slot pick (`fn_8003FD50(4)` at 0x2118) are untouched; watch for a hang or odd behaviour.
- Practice from Minigame Mode uses the first table match (the 4P entry), so the patch is inactive there.
- The Duel choice screen (`fn_801F0BCC`) was not checked for fixed per-game tables like the Battle thumbnail table; if the game crashes when m609/m618 is offered in a Duel, look there first.

Dolphin tests: Duel space offers Daft Rafts / Lift Leapers; only two rafts race / two lifts move; the game ends when a duelist finishes; 4P play of both games is unchanged; result screen shows the right winner.

## Test aid: `tools/patches/test_aids/apply_duel_test_aid_patch.py`
Minigame Mode cannot launch the duel entries (it resolves the game through `MgNoGet`, which returns the first match, the 4P entry), so the duel versions only run from a Duel space. The test aid makes the Duel space always offer entry 86 (Daft Rafts) and 87 (Lift Leapers) as choices 1 and 2: `fn_801F0BCC` joins all its pickers at `0x801F0F7C`, and that `lis` is replaced by a `bl` to a cave at `0x802F7CA0` that overwrites the first two s16 choices when type = 6. Run `python -m tools.patches.test_aids.apply_duel_test_aid_patch --remove` (then copy `main.dol` to root) to take it out. Deployed to root; not yet tested in Dolphin.
