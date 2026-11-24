"""CPU board AI in Party Mode (forks, Sluggish 'Shroom, orb use, Orb Hut): python -m tools.patches.apply_cpu_landing_patch

- Forks (hook 0x801EF484, BranchComChoiceGet): the CPU prefers a branch that lands on a Miracle,
  Duel or Bowser/DK space, after a Star it can buy if there is one.
- Sluggish 'Shroom: the CPU picks the roll it wants and uses the orb only when there is one;
  the dice launch (0x8015435C) gets that roll as the die's target face.
- Orb use (mbCapSelectComGet, 0x801C9C18, 0x801C9CD0, 0x801C9D08): the 30% "use nothing" roll is
  removed, so a CPU holding a usable orb uses one every turn.
- Orb Hut (ev_Shop, 0x801EAE14): a CPU only buys an orb that leaves it 20+ coins, trying Super,
  Sluggish and plain Mushroom first.

The full rules are in the comment block below. Code lives in the init-section caves listed in
CAVES (zero padding between TRK vector slots, 0x80003C18-0x80004CE4).

Writes main.dol and the .text and init listings. No prerequisites. Idempotent.
"""
import struct

from tools.lib.paths import ASM_INIT, ASM_TEXT, DOL
from tools.lib.dol import dol_offset, encode_branch, patch_asm_word
from tools.patches.apply_dk_bonus_patch import patch_text_word
from tools.patches.apply_star_trap_orb_patch import (
    CONDITIONS, add, addi, blr, branch, cmpw, cmpwi, cond, li, lis, lwz, mflr, mr, mtlr, slwi, stw, stwu,
)

# CPU board AI, Party Mode:
#
# 1. Forks (hook on fn_801EF484, BranchComChoiceGet). The CPU simulates every branch for
#    exactly the remaining dice steps (GwPlayer.moveNum). If a branch reaches a Star it can
#    buy (20+ coins), it prefers a branch that also lands on a Miracle (space type 4), Duel
#    (5) or Bowser/DK (6) space after the Star, else keeps the vanilla Star chase. With no
#    Star in reach it takes a branch that lands exactly on one of those spaces. Lowest
#    priority, with no Star in reach and none of those: a branch landing on a Happening (3)
#    or Orb (8) space, the one nearest a Star if several. (Not used for the Sluggish Shroom.)
#
# 2. Sluggish 'Shroom (orb 2 -> diceMode 3 -> dice type 14). pick() returns the roll the
#    CPU wants: with a Star within 10 steps and 20+ coins, a roll that lands on one of the
#    spaces above AFTER the Star (Miracle first), else 10; with no Star, a roll that lands
#    exactly on one of those spaces; else 0.
#    - mbCapSelectComGet: a CPU holding the orb uses it whenever pick() > 0, and its draw
#      chance is forced to 0 otherwise, so the CPU saves the orb.
#    - Every other orb: the 30% "use nothing" roll is removed and an orb whose table chance
#      is 0 gets chance 1, so a CPU holding an orb uses one every turn (weights still favour
#      the preferred orbs; orbs unknown to the AI table and unplaceable traps stay unused).
#    - Orb Hut (ev_Shop): a CPU only buys an orb that leaves it with 20+ coins, trying Super
#      Mushroom, Sluggish Mushroom and Mushroom (in that order) before any other orb.
#    - Dice launch: the CPU's Sluggish die gets the picked roll as its target face. The
#      vanilla CPU code (fn_80186558) already waits for that face before pressing A.
HOOK = 0x801EF484
HOOK_ORIGINAL = 0x9421FFD0  # stwu r1, -0x30(r1)
HOOK_RETURN = 0x801EF488
FN_PLAYER_WORK = 0x801537C4  # mbPlayerWorkGet; +0xE = forced target space

# Zero padding between TRK vector slots (51 words each unless noted).
CAVES = {
    "main": (0x80004A18, 0x80004BE4),  # 115 words
    "fork2": (0x80004218, 0x800042E4),
    "fork3": (0x80004C18, 0x80004CE4),
    "pick1": (0x80003C18, 0x80003CE4),
    "pick2": (0x80003D18, 0x80003DE4),
    "select": (0x80003E18, 0x80003EE4),
    "launch": (0x80004418, 0x800044E4),
    "shop": (0x80004318, 0x800043E4),
}

STAR_TYPE = 7
HAPPENING_TYPE = 3  # "?" space
ORB_TYPE = 8  # orb space (mbCapMasuExec)
FN_STAR_DIST = 0x80178BA8  # (space, type, ?, ?) -> steps to the nearest space of that type
STAR_COINS = 20
MAX_BRANCHES = 8
MAX_STEPS = 20

SLUGGISH_ID = 2  # orb id
BOO_AWAY_ID = 31  # passive orb (Boo-away): never actively used, so the CPU keeps it
SLUGGISH_DICE_TYPE = 14
# The CPU presses when the displayed face index equals target-1, so the roll lands on face
# index `target` (roll = index + 1). Adjust if Dolphin shows an off-by-one.
ROLL_TO_TARGET = -1
SELECT_HOOK = 0x801C9C18  # lis r3, 0x8028 (mbCapSelectComGet, after the count check)
SELECT_HOOK_ORIGINAL = 0x3C608028
SELECT_RETURN = 0x801C9FF0  # epilogue; r3 = chosen slot
CHANCE_HOOK = 0x801C9D08  # stw r3, 8(r30) (store of mbCapComChanceGet result)
CHANCE_HOOK_ORIGINAL = 0x907E0008
SKIP_HOOK = 0x801C9CD0  # bge past the "30%: use no orb" roll -> always skip the roll
SKIP_HOOK_ORIGINAL = 0x4080000C
SKIP_TARGET = 0x801C9CDC
SHOP_HOOK = 0x801EAE14  # li r30, 0 (ev_Shop: CPU scan for the first affordable orb)
SHOP_HOOK_ORIGINAL = 0x3BC00000
SHOP_RETURN = 0x801EAE4C  # cmpw r30, r26 (r30 == r26: buy nothing)
FN_COINS = 0x8015C770
SHOP_MIN_COINS_LEFT = 20
SHOP_PRIORITY = (1, 2, 0)  # Super Mushroom, Sluggish Mushroom, Mushroom
LAUNCH_HOOK = 0x8015435C  # slwi r0, r25, 2 (dice launch, per-die target)
LAUNCH_HOOK_ORIGINAL = 0x5720103A

CONDITIONS.setdefault("bgt", 0x41810000)
CONDITIONS.setdefault("blt", 0x41800000)


def lha(rd, offset, ra):
    return f"lha r{rd}, {offset:#x}(r{ra})", 0xA8000000 | rd << 21 | ra << 16 | offset & 0xFFFF


def lhz(rd, offset, ra):
    return f"lhz r{rd}, {offset:#x}(r{ra})", 0xA0000000 | rd << 21 | ra << 16 | offset & 0xFFFF


def lbz(rd, offset, ra):
    return f"lbz r{rd}, {offset:#x}(r{ra})", 0x88000000 | rd << 21 | ra << 16 | offset & 0xFFFF


def lhzx(rd, ra, rb):
    return f"lhzx r{rd}, r{ra}, r{rb}", 0x7C00022E | rd << 21 | ra << 16 | rb << 11


def lbzx(rd, ra, rb):
    return f"lbzx r{rd}, r{ra}, r{rb}", 0x7C0000AE | rd << 21 | ra << 16 | rb << 11


def stbx(rs, ra, rb):
    return f"stbx r{rs}, r{ra}, r{rb}", 0x7C0001AE | rs << 21 | ra << 16 | rb << 11


def stmw(rs, offset, ra):
    return f"stmw r{rs}, {offset:#x}(r{ra})", 0xBC000000 | rs << 21 | ra << 16 | offset & 0xFFFF


def lmw(rd, offset, ra):
    return f"lmw r{rd}, {offset:#x}(r{ra})", 0xB8000000 | rd << 21 | ra << 16 | offset & 0xFFFF


def extsh(ra, rs):
    return f"extsh r{ra}, r{rs}", 0x7C000734 | rs << 21 | ra << 16


def extsb(ra, rs):
    return f"extsb r{ra}, r{rs}", 0x7C000774 | rs << 21 | ra << 16


def mulli(rd, ra, imm):
    return f"mulli r{rd}, r{ra}, {imm:#x}", 0x1C000000 | rd << 21 | ra << 16 | imm & 0xFFFF


def andi_dot(ra, rs, imm):
    return f"andi. r{ra}, r{rs}, {imm:#x}", 0x70000000 | rs << 21 | ra << 16 | imm & 0xFFFF


def and_dot(ra, rs, rb):
    return f"and. r{ra}, r{rs}, r{rb}", 0x7C000039 | rs << 21 | ra << 16 | rb << 11


def or_(ra, rs, rb):
    return f"or r{ra}, r{rs}, r{rb}", 0x7C000378 | rs << 21 | ra << 16 | rb << 11


def slw(ra, rs, rb):
    return f"slw r{ra}, r{rs}, r{rb}", 0x7C000030 | rs << 21 | ra << 16 | rb << 11


def lwzx(rd, ra, rb):
    return f"lwzx r{rd}, r{ra}, r{rb}", 0x7C00002E | rd << 21 | ra << 16 | rb << 11


def lhax(rd, ra, rb):
    return f"lhax r{rd}, r{ra}, r{rb}", 0x7C0002AE | rd << 21 | ra << 16 | rb << 11


def lwz_sda(rd, offset):
    # lbl_XXXXXXXX@sda21(r0) relocation: displacement from r13
    return f"lwz r{rd}, {offset:#x}(r13)", 0x80000000 | rd << 21 | 13 << 16 | offset & 0xFFFF


def addi_sda(rd, offset):
    return f"addi r{rd}, r13, {offset:#x}", 0x38000000 | rd << 21 | 13 << 16 | offset & 0xFFFF


def entry_code():
    return [
        # ---- hook entry: only CPU real choices (flag == 0) are handled -------------------
        ("label", "entry"),
        cmpwi(6, 0), cond("bne", "orig"),
        stwu(1, -0x40, 1), mflr(0), stw(0, 0x44, 1),
        stmw(23, 0x10, 1),
        stw(3, 0x8, 1),
        mr(31, 4), mr(30, 5),
        cmpwi(31, 2), cond("blt", "fail"),
        cmpwi(31, MAX_BRANCHES), cond("bgt", "fail"),
        # a forced target (+0xE) keeps the vanilla behaviour
        branch(FN_PLAYER_WORK, link=True),
        lha(0, 0xE, 3), cmpwi(0, 0), cond("bne", "fail"),
        lwz(3, 0x8, 1),
        mulli(4, 3, 0x108), lis(3, 0x8028), addi(3, 3, 0x2E70), add(28, 3, 4),
        lbz(0, 0xA, 28), extsb(29, 0),  # r29 = moveNum
        cmpwi(29, 1), cond("blt", "fail"),
        cmpwi(29, MAX_STEPS), cond("bgt", "fail"),
        lha(0, 0x1C, 28), li(27, 0), cmpwi(0, STAR_COINS), cond("blt", "nostar"), li(27, 1),
        ("label", "nostar"),
        lha(28, 0xC, 28),  # r28 = current space
        # pass 1: simulate every branch, keep a result mask per branch
        li(26, 0), li(25, 0),
        branch("pass1"),
        ("split", None),
        ("label", "pass1"),
        cmpw(26, 31), cond("bge", "pass1_done"),
        slwi(0, 26, 1), lhax(3, 30, 0),
        addi(4, 29, -1), mr(5, 28), mr(6, 27), li(7, 0), branch("visit", link=True),
        addi(4, 1, 0x38), stbx(3, 4, 26),
        or_(25, 25, 3),
        addi(26, 26, 1), branch("pass1"),
        ("label", "pass1_done"),
        # no Star in reach: Miracle (2), Duel (4), Bowser/DK (8) landings.
        # Star in reach: only landings after passing it (0x20, 0x40, 0x80).
        li(24, 2), li(23, 8), andi_dot(0, 25, 1), cond("beq", "outer"),
        li(24, 0x20), li(23, 0x80),
        ("label", "outer"),
        li(26, 0),
        ("label", "inner"),
        cmpw(26, 31), cond("bge", "next_bit"),
        addi(4, 1, 0x38), lbzx(0, 4, 26), and_dot(0, 0, 24), cond("bne", "found"),
        addi(26, 26, 1), branch("inner"),
        ("label", "next_bit"),
        slwi(24, 24, 1), cmpw(24, 23), cond("ble", "outer"),
        # lowest priority, only with no Star in reach: a branch that lands on a Happening or
        # Orb space (mask bit 0x10); among those, the one nearest to a Star (fn_80178BA8).
        andi_dot(0, 25, 1), cond("bne", "fail"),
        branch("act_stage"),
        ("split", None),
        ("label", "act_stage"),
        li(24, -1), li(23, 0x270F), li(26, 0),
        ("label", "aloop"),
        cmpw(26, 31), cond("bge", "adone"),
        addi(4, 1, 0x38), lbzx(0, 4, 26), andi_dot(0, 0, 0x10), cond("beq", "anext"),
        slwi(0, 26, 1), lhax(3, 30, 0), li(4, STAR_TYPE), li(5, 1), li(6, 1),
        branch(FN_STAR_DIST, link=True),
        cmpw(3, 23), cond("bge", "anext"),
        mr(24, 26), mr(23, 3),
        ("label", "anext"),
        addi(26, 26, 1), branch("aloop"),
        ("label", "adone"),
        cmpwi(24, 0), cond("blt", "fail"),
        mr(26, 24), branch("found"),
        ("label", "fail"),
        lwz(3, 0x8, 1), mr(4, 31), mr(5, 30), li(6, 0),
        lmw(23, 0x10, 1), lwz(0, 0x44, 1), mtlr(0), addi(1, 1, 0x40),
        ("label", "orig"),
        stwu(1, -0x30, 1), branch(HOOK_RETURN),
        ("label", "found"),
        mr(3, 26),
        lmw(23, 0x10, 1), lwz(0, 0x44, 1), mtlr(0), addi(1, 1, 0x40), blr(),
    ]


def visit_code():
    # visit(space r3, steps left r4, previous space r5, starOK r6, starPassed r7) -> mask
    # mask: bit 0 = a buyable Star was reached; bits 1-3 = lands on Miracle/Duel/Bowser-DK;
    # bits 5-7 = the same landings after passing the Star on that path.
    return [
        ("label", "visit"),
        stwu(1, -0x40, 1), mflr(0), stw(0, 0x44, 1), stmw(23, 0x10, 1),
        mr(31, 3), mr(30, 4), mr(29, 5), mr(28, 6), mr(23, 7),
        lwz_sda(0, 0x9930), slwi(0, 0, 2), addi_sda(4, 0x9924), lwzx(4, 4, 0),
        extsh(0, 31), mulli(0, 0, 0x70), add(27, 4, 0),
        lhz(5, 0x30, 27),
        li(24, 0),
        cmpwi(5, STAR_TYPE), cond("bne", "notstar"),
        cmpwi(28, 0), cond("beq", "notstar"),
        li(24, 1), li(23, 1),
        ("label", "notstar"),
        cmpwi(30, 0), cond("bne", "walk"),
        cmpwi(5, HAPPENING_TYPE), cond("beq", "action"), cmpwi(5, ORB_TYPE), cond("bne", "target"),
        ("label", "action"),
        li(3, 0x10), or_(24, 24, 3), branch("vend"),
        ("label", "target"),
        addi(4, 5, -3), cmpwi(4, 1), cond("blt", "vend"), cmpwi(4, 3), cond("bgt", "vend"),
        li(3, 1), slw(3, 3, 4), cmpwi(23, 0), cond("beq", "plain"), slwi(3, 3, 4),
        ("label", "plain"),
        or_(24, 24, 3), branch("vend"),
        ("label", "walk"),
        lhz(25, 0x64, 27), li(26, 0),
        ("label", "loop"),
        cmpw(26, 25), cond("bge", "vend"),
        slwi(4, 26, 1), addi(4, 4, 0x66), lhzx(3, 27, 4), extsh(3, 3),
        cmpw(3, 29), cond("beq", "next"),
        addi(4, 30, -1), mr(5, 31), mr(6, 28), mr(7, 23), branch("visit", link=True),
        or_(24, 24, 3),
        ("label", "next"),
        addi(26, 26, 1), branch("loop"),
        ("label", "vend"),
        mr(3, 24),
        lmw(23, 0x10, 1), lwz(0, 0x44, 1), mtlr(0), addi(1, 1, 0x40), blr(),
    ]


def pick_code():
    # pick(player r3) -> roll 1-10 the CPU wants from a Sluggish Shroom, or 0 if none.
    # 1. Star in reach (20+ coins): a roll that lands on Miracle/Duel/Bowser/DK after the
    #    Star (Miracle first), otherwise 10.
    # 2. Otherwise a roll that lands exactly on Miracle/Duel/Bowser/DK (Miracle first).
    return [
        ("label", "pick"),
        stwu(1, -0x50, 1), mflr(0), stw(0, 0x54, 1), stmw(23, 0x10, 1),
        mulli(4, 3, 0x108), lis(3, 0x8028), addi(3, 3, 0x2E70), add(5, 3, 4),
        lha(31, 0xC, 5), lha(30, 0xE, 5),
        lha(0, 0x1C, 5), li(29, 0), cmpwi(0, STAR_COINS), cond("blt", "pk_nostar"), li(29, 1),
        ("label", "pk_nostar"),
        lwz_sda(0, 0x9930), slwi(0, 0, 2), addi_sda(4, 0x9924), lwzx(4, 4, 0),
        extsh(0, 31), mulli(0, 0, 0x70), add(24, 4, 0),
        li(23, 0), li(28, 1),
        ("label", "rloop"),
        cmpwi(28, 10), cond("bgt", "rdone"),
        li(25, 0), lhz(26, 0x64, 24), li(27, 0),
        ("label", "lloop"),
        cmpw(27, 26), cond("bge", "ldone"),
        slwi(4, 27, 1), addi(4, 4, 0x66), lhzx(3, 24, 4), extsh(3, 3),
        cmpw(3, 30), cond("beq", "lnext"),
        addi(4, 28, -1), mr(5, 31), mr(6, 29), li(7, 0), branch("visit", link=True),
        or_(25, 25, 3),
        ("label", "lnext"),
        addi(27, 27, 1), branch("lloop"),
        ("label", "ldone"),
        addi(4, 1, 0x37), stbx(25, 4, 28),
        or_(23, 23, 25),
        addi(28, 28, 1), branch("rloop"),
        ("split", None),
        ("label", "rdone"),
        li(27, 0), li(26, 2), li(25, 8), andi_dot(0, 23, 1), cond("beq", "pk_bits"),
        li(27, 4), slw(26, 26, 27), slw(25, 25, 27),
        ("label", "pk_bits"),
        li(28, 1),
        ("label", "rr"),
        cmpwi(28, 10), cond("bgt", "nextbit"),
        addi(4, 1, 0x37), lbzx(0, 4, 28), and_dot(0, 0, 26), cond("bne", "pk_found"),
        addi(28, 28, 1), branch("rr"),
        ("label", "nextbit"),
        slwi(26, 26, 1), cmpw(26, 25), cond("ble", "pk_bits"),
        li(3, 0), andi_dot(0, 23, 1), cond("beq", "pk_out"),
        li(3, 10), branch("pk_out"),
        ("label", "pk_found"),
        mr(3, 28),
        ("label", "pk_out"),
        lmw(23, 0x10, 1), lwz(0, 0x54, 1), mtlr(0), addi(1, 1, 0x50), blr(),
    ]


def select_hooks():
    # H1 (mbCapSelectComGet after the count check): a CPU holding a Sluggish 'Shroom uses
    # it whenever pick() finds a roll. H2: otherwise its draw chance is forced to 0, so the
    # CPU keeps the orb until it can get a Star and/or a space of interest.
    return [
        ("label", "sel_hook"),
        li(31, 0),
        ("label", "sel_loop"),
        cmpw(31, 29), cond("bge", "sel_none"),
        slwi(0, 31, 2), lwzx(0, 24, 0), cmpwi(0, SLUGGISH_ID), cond("beq", "sel_found"),
        addi(31, 31, 1), branch("sel_loop"),
        ("label", "sel_found"),
        mr(3, 23), branch("pick", link=True), cmpwi(3, 0), cond("ble", "sel_none"),
        mr(3, 31), branch(SELECT_RETURN),
        ("label", "sel_none"),
        lis(3, 0x8028), branch(SELECT_HOOK + 4),
        ("label", "chance_hook"),
        lwz(0, 4, 30), cmpwi(0, SLUGGISH_ID), cond("beq", "chance_zero"),
        cmpwi(0, BOO_AWAY_ID), cond("bne", "chance_other"),
        ("label", "chance_zero"),
        li(3, 0), branch("chance_keep"),
        ("label", "chance_other"),
        cmpwi(3, 0), cond("bne", "chance_keep"), li(3, 1),
        ("label", "chance_keep"),
        stw(3, 8, 30), branch(CHANCE_HOOK + 4),
    ]


def launch_hook():
    # H3 (dice launch): a CPU rolling the Sluggish dice (type 14) aims at the roll pick()
    # chose. Target = roll + ROLL_TO_TARGET (the CPU presses when the face before it shows).
    return [
        ("label", "launch_hook"),
        cmpwi(24, SLUGGISH_DICE_TYPE), cond("bne", "lh_back"),
        mulli(4, 31, 0x108), lis(3, 0x8028), addi(3, 3, 0x2E70), lbzx(0, 3, 4),
        andi_dot(0, 0, 0x20), cond("beq", "lh_back"),
        mr(3, 31), branch("pick", link=True), cmpwi(3, 0), cond("ble", "lh_back"),
        addi(29, 3, ROLL_TO_TARGET),
        ("label", "lh_back"),
        slwi(0, 25, 2), branch(LAUNCH_HOOK + 4),
    ]


def srw(ra, rs, rb):
    return f"srw r{ra}, r{rs}, r{rb}", 0x7C000430 | rs << 21 | ra << 16 | rb << 11


def subf(rd, ra, rb):
    return f"subf r{rd}, r{ra}, r{rb}", 0x7C000050 | rd << 21 | ra << 16 | rb << 11


def shop_hook():
    # ev_Shop, CPU branch. The shop list is r1+0x1bc, 0x1c bytes per orb: +0 id, +4 price;
    # r26 = orb count. Pick the first orb of SHOP_PRIORITY that leaves the CPU with
    # SHOP_MIN_COINS_LEFT coins after paying, else any such orb; else r30 = r26 (buy nothing).
    packed = sum(orb << (4 * rank) for rank, orb in enumerate(SHOP_PRIORITY))
    code = [
        ("label", "shop_hook"),
        lwz(3, 0, 31), branch(FN_COINS, link=True), mr(12, 3),
        li(11, 0),
        ("label", "prio"),
        cmpwi(11, len(SHOP_PRIORITY)), cond("bge", "general"),
        li(10, packed), slwi(0, 11, 2), srw(10, 10, 0), andi_dot(10, 10, 0xF),
        li(30, 0),
        ("label", "scan"),
        cmpw(30, 26), cond("bge", "next_prio"),
        mulli(5, 30, 0x1C), addi(9, 1, 0x1BC), lwzx(8, 9, 5), cmpw(8, 10), cond("bne", "skip"),
        addi(5, 5, 4), lwzx(7, 9, 5), subf(6, 7, 12), cmpwi(6, SHOP_MIN_COINS_LEFT),
        cond("bge", "shop_done"),
        ("label", "skip"),
        addi(30, 30, 1), branch("scan"),
        ("label", "next_prio"),
        addi(11, 11, 1), branch("prio"),
        ("label", "general"),
    ]
    code += [
        li(30, 0),
        ("label", "gscan"),
        cmpw(30, 26), cond("bge", "shop_done"),
        mulli(5, 30, 0x1C), addi(9, 1, 0x1BC), addi(5, 5, 4), lwzx(7, 9, 5), subf(6, 7, 12),
        cmpwi(6, SHOP_MIN_COINS_LEFT), cond("bge", "shop_done"),
        addi(30, 30, 1), branch("gscan"),
        ("label", "shop_done"),
        branch(SHOP_RETURN),
    ]
    return code


def assemble_segments(segments):
    """segments: [(base, limit, items)]; labels are global across segments."""
    labels = {}
    for base, limit, items in segments:
        pc = base
        for item in items:
            if item[0] == "label":
                labels[item[1]] = pc
            else:
                pc += 4
        if pc > limit:
            raise RuntimeError(f"Code cave overflow at {pc:#x} (limit {limit:#x})")
    words = []
    for base, limit, items in segments:
        pc = base
        for item in items:
            if item[0] == "label":
                continue
            if item[0] == "b":
                _, target, link = item
                target = labels.get(target, target)
                word = encode_branch(pc, target, link)
                text = f"b{'l' if link else ''} 0x{target:08X}"
            elif item[0] in CONDITIONS:
                _, target, opcode = item
                displacement = labels[target] - pc
                if not -0x8000 <= displacement < 0x8000:
                    raise RuntimeError("Conditional branch out of range")
                word = opcode | displacement & 0xFFFC
                text = f"{item[0]} .L_{labels[target]:08X}"
            else:
                text, word = item
            words.append((pc, word, text))
            pc += 4
    return words, labels


def is_cave_branch(address, word):
    if word >> 26 != 0x12 or word & 3:
        return False
    displacement = word & 0x03FFFFFC
    if displacement & 0x02000000:
        displacement -= 0x04000000
    return 0x80003800 <= address + displacement < 0x80004E00


def main():
    text_asm = ASM_TEXT.read_bytes().decode("utf-8")
    init_asm = ASM_INIT.read_bytes().decode("utf-8")
    dol = bytearray(DOL.read_bytes())

    entry = entry_code()
    splits = [i for i, item in enumerate(entry) if item == ("split", None)]
    pick = pick_code()
    p_split = pick.index(("split", None))
    segments = [
        (*CAVES["main"], visit_code() + entry[:splits[0]]),
        (*CAVES["fork2"], entry[splits[0] + 1:splits[1]]),
        (*CAVES["fork3"], entry[splits[1] + 1:]),
        (*CAVES["pick1"], pick[:p_split]),
        (*CAVES["pick2"], pick[p_split + 1:]),
        (*CAVES["select"], select_hooks()),
        (*CAVES["launch"], launch_hook()),
        (*CAVES["shop"], shop_hook()),
    ]
    words, labels = assemble_segments(segments)
    # Every cave word must be zero or already ours; stale words of an older run are cleared.
    for start, end in CAVES.values():
        for address in range(start, end, 4):
            struct.pack_into(">I", dol, dol_offset(dol, address), 0)
            init_asm = patch_asm_word(init_asm, address, 0, "invalid", allowed=None)
    for address, word, mnemonic in words:
        struct.pack_into(">I", dol, dol_offset(dol, address), word)
        init_asm = patch_asm_word(init_asm, address, word, mnemonic, allowed=None)

    for address, original, target in (
        (HOOK, HOOK_ORIGINAL, labels["entry"]),
        (SELECT_HOOK, SELECT_HOOK_ORIGINAL, labels["sel_hook"]),
        (CHANCE_HOOK, CHANCE_HOOK_ORIGINAL, labels["chance_hook"]),
        (LAUNCH_HOOK, LAUNCH_HOOK_ORIGINAL, labels["launch_hook"]),
        (SHOP_HOOK, SHOP_HOOK_ORIGINAL, labels["shop_hook"]),
    ):
        position = dol_offset(dol, address)
        found = struct.unpack_from(">I", dol, position)[0]
        hook_word = encode_branch(address, target)
        if found != original and not is_cave_branch(address, found):
            raise RuntimeError(f"Unexpected word at {address:08X}: {found:08X}")
        struct.pack_into(">I", dol, position, hook_word)
        text_asm = patch_text_word(text_asm, address, hook_word, f"b 0x{target:08X}")

    position = dol_offset(dol, SKIP_HOOK)
    found = struct.unpack_from(">I", dol, position)[0]
    skip_word = encode_branch(SKIP_HOOK, SKIP_TARGET)
    if found not in (SKIP_HOOK_ORIGINAL, skip_word):
        raise RuntimeError(f"Unexpected word at {SKIP_HOOK:08X}: {found:08X}")
    struct.pack_into(">I", dol, position, skip_word)
    text_asm = patch_text_word(text_asm, SKIP_HOOK, skip_word, ".L_801C9CDC".join(["b ", ""]))

    ASM_TEXT.write_bytes(text_asm.encode("utf-8"))
    ASM_INIT.write_bytes(init_asm.encode("utf-8"))
    DOL.write_bytes(dol)
    print(f"CPU landing + Sluggish patch: {len(words)} words")


if __name__ == "__main__":
    main()
