"""Star Trap Orb: a new hit orb that steals a Star: python -m tools.patches.apply_star_trap_orb_patch

A player who lands on it loses 1 Star (if they have one) and the owner gains it. Orb ID 14,
reusing the Piranha handler (fn_801A3BC8): five of its coin sites branch on the orb ID. Costs
10 coins and is offered about as often as a typical orb on the six main boards (STAR_TRAP_ODDS).

- DOL: orb data (lbl_80266BDC) and event table (lbl_80268500) rows, and code in the
  init-section caves REGIONS (0x80003830-0x80003BE4, after the Bowser and DK caves). A hook at
  the end of mbCapListRead appends the orb to each board's shop list at run time.
- capsule.bin: appends the orb model tools/assets/mp6dx_soluna_orb.hsf as entry 85 (0x140055),
  rebuilt from the original file.
- Messages, every language: bank 54 records 21-22 (event), bank 55 record 59 (description),
  bank 56 record 37 (name), appended with append_records. English chains onto the current
  output; the other languages are built from the original files.

Writes main.dol, the .text, .data and init listings, files/mess/messdata*.bin and
files/data/capsule.bin. No prerequisites. castaway_wheel appends its model to capsule.bin after
this one, so it must run later. Idempotent.
"""
import struct
import zlib

from tools.lib.paths import ASM_DATA, ASM_INIT, ASM_TEXT, BUILD, DOL, MESS_OUTPUT, ROOT
from tools.lib.dol import dol_offset, encode_branch, patch_asm_word
from tools.patches.apply_dk_bonus_patch import patch_text_word
from tools.lib.messages import append_records

# Star Trap Orb: a Piranha-style hit orb. A player who lands on it loses 1 Star
# (if they have one) and the owner gains it. The vanilla Piranha handler
# (fn_801A3BC8) is reused; five of its coin sites branch on the orb ID.
STAR_TRAP_ID = 14
PIRANHA_ID = 12
# Orb icon shown in the shop and inventory. Model: 0x140000-0x140016 (one per orb, see the
# capsuleData table), 0x140021 or 0x140022. Frame: 0x14001C self (green), 0x14001D hit (yellow),
# 0x14001E trap (red), 0x14001F defensive (teal), 0x140020 Miracle (purple). Colour (0-3) is
# the trail colour and normally matches the frame's category.
STAR_TRAP_MODEL = 0x00140055  # Soluna sun icon, appended to capsule.bin as entry 85
STAR_TRAP_FRAME = 0x0014001D
STAR_TRAP_COLOUR = 1
STAR_TRAP_PRICE = 10
STAR_TRAP_RARITY = 0x44  # 'D'
# How often the orb is offered. "average": in every board list with at least
# STAR_TRAP_MIN_LIST orbs (the six main boards), its weight in each weight group and rank is
# the average of the non-zero weights already there, so it is about as common as a typical
# orb. "boost": fixed weight STAR_TRAP_TEST_WEIGHT in every list (testing; roughly 50%).
STAR_TRAP_ODDS = "average"
STAR_TRAP_MIN_LIST = 5
STAR_TRAP_TEST_WEIGHT = 100

NAME_MESSAGE = 37  # bank 56 (CAPSULE_EX98) record
DESC_MESSAGE = 59  # bank 55 (CAPSULE_EX99) record
EVENT_BANK = 54  # bank 0x36, CAPSULE_EX02: Piranha's own event messages
EVENT_TAKEN = 21
EVENT_NONE = 22

CAPSULE_DATA = "lbl_80266BDC"
CAPSULE_DATA_ROW_WORDS = 10
EVENT_TABLE = "lbl_80268500"
EVENT_TABLE_ROW_WORDS = 7

LIST_BUFFER = 0x802DA940
LIST_MAX_ENTRIES = 32  # buffer holds 33 entries; one slot is kept for the -1 terminator

# Free zero runs inside the TRK vector padding, after the Bowser and DK caves.
REGIONS = {
    "a": (0x80003830, 0x800038E4),
    "b": (0x80003918, 0x800039E4),
    "c": (0x80003A18, 0x80003AE4),
    "d": (0x80003B18, 0x80003BE4),
}

FN_STAR_GET = 0x8015CE98
FN_STAR_ADD = 0x8015CF64
FN_STAR_POPUP = 0x80181DDC
FN_STAR_POPUP_DONE = 0x80182258
FN_STATUS_SHOW = 0x80186258
FN_YIELD = 0x8000E2C4

CAPSULE_SOURCE = ROOT / "orig" / "GP6P01" / "files" / "data" / "capsule.bin"
CAPSULE_OUTPUT = BUILD / "files" / "data" / "capsule.bin"
ASSETS = ROOT / "tools" / "assets"
# Models appended to capsule.bin, in order; the first becomes entry 85 (file id 0x140055).
CAPSULE_NEW_ENTRIES = ("mp6dx_soluna_orb.hsf",)

MESS_NAMES = (
    "messdata.bin",
    "messdata_eng.bin",
    "messdata_fra.bin",
    "messdata_ger.bin",
    "messdata_ita.bin",
    "messdata_spa.bin",
)
MESS_SOURCE_DIR = ROOT / "orig" / "GP6P01" / "files" / "mess"
MESS_OUTPUT_DIR = BUILD / "files" / "mess"


def pad4(record):
    return record + b"\0" * (-len(record) % 4)


MESSAGE_ADDITIONS = {
    EVENT_BANK: (
        21,
        [
            pad4(b"\x00\x15\x00\x03One\x10of\x10your\x10Stars\x10was\x10stolen\xc2\xff\x00"),
            pad4(b"\x00\x15\x00\x03You\x10don\\t\x10have\x10a\x10Star\x10to\x10take\xc2\xff\x00"),
        ],
    ),
    55: (
        59,
        [pad4(
            b"\x00\x15\x00\x03Star\x10Trap\x10Orb\x1e\x05\x10]Use\x10on\x10a\x10space^\x1e\x08\n"
            b"Any\x10opponent\x10who\x10lands\x10on\x10it\x10must\x10\n"
            b"give\x10you\x10a\x10Star\x85\x00"
        )],
    ),
    56: (37, [pad4(b"\x00\x07\x00\x01Star\x10Trap\x00")]),
}


def lwz(rd, offset, ra):
    return f"lwz r{rd}, {offset:#x}(r{ra})", 0x80000000 | rd << 21 | ra << 16 | offset & 0xFFFF


def stw(rs, offset, ra):
    return f"stw r{rs}, {offset:#x}(r{ra})", 0x90000000 | rs << 21 | ra << 16 | offset & 0xFFFF


def stwu(rs, offset, ra):
    return f"stwu r{rs}, -{-offset:#x}(r{ra})", 0x94000000 | rs << 21 | ra << 16 | offset & 0xFFFF


def stb(rs, offset, ra):
    return f"stb r{rs}, {offset:#x}(r{ra})", 0x98000000 | rs << 21 | ra << 16 | offset & 0xFFFF


def lbzx(rd, ra, rb):
    return f"lbzx r{rd}, r{ra}, r{rb}", 0x7C0000AE | rd << 21 | ra << 16 | rb << 11


def stbx(rs, ra, rb):
    return f"stbx r{rs}, r{ra}, r{rb}", 0x7C0001AE | rs << 21 | ra << 16 | rb << 11


def add(rd, ra, rb):
    return f"add r{rd}, r{ra}, r{rb}", 0x7C000214 | rd << 21 | ra << 16 | rb << 11


def slwi(ra, rs, n):
    return f"slwi r{ra}, r{rs}, {n}", 0x54000000 | rs << 21 | ra << 16 | n << 11 | (31 - n) << 1


def srwi(ra, rs, n):
    return (
        f"srwi r{ra}, r{rs}, {n}",
        0x54000000 | rs << 21 | ra << 16 | (32 - n) << 11 | n << 6 | 31 << 1,
    )


def divw(rd, ra, rb):
    return f"divw r{rd}, r{ra}, r{rb}", 0x7C0003D6 | rd << 21 | ra << 16 | rb << 11


def cmpwi(reg, imm):
    return f"cmpwi r{reg}, {imm:#x}", 0x2C000000 | reg << 16 | imm & 0xFFFF


def cmpw(ra, rb):
    return f"cmpw r{ra}, r{rb}", 0x7C000000 | ra << 16 | rb << 11


def lis(rd, imm):
    return f"lis r{rd}, {imm:#x}", 0x3C000000 | rd << 21 | imm & 0xFFFF


def addi(rd, ra, imm):
    text = f"addi r{rd}, r{ra}, {imm:#x}" if imm >= 0 else f"addi r{rd}, r{ra}, -{-imm:#x}"
    return text, 0x38000000 | rd << 21 | ra << 16 | imm & 0xFFFF


def li(reg, imm):
    text = f"li r{reg}, {imm:#x}" if imm >= 0 else f"li r{reg}, -{-imm:#x}"
    return text, 0x38000000 | reg << 21 | imm & 0xFFFF


def mr(ra, rs):
    return f"mr r{ra}, r{rs}", 0x7C000378 | rs << 21 | ra << 16 | rs << 11


def mflr(reg):
    return f"mflr r{reg}", 0x7C0802A6 | reg << 21


def mtlr(reg):
    return f"mtlr r{reg}", 0x7C0803A6 | reg << 21


def blr():
    return "blr", 0x4E800020


def beqlr():
    return "beqlr", 0x4D820020


def branch(target, link=False):
    return ("b", target, link)


CONDITIONS = {
    "beq": 0x41820000,
    "bne": 0x40820000,
    "bge": 0x40800000,
    "blt": 0x41800000,
    "ble": 0x40810000,
}


def cond(mnemonic, target):
    return (mnemonic, target, CONDITIONS[mnemonic])


def assemble(base, items, limit):
    labels = {}
    pc = base
    for item in items:
        if item[0] == "label":
            labels[item[1]] = pc
        else:
            pc += 4
    if pc > limit:
        raise RuntimeError(f"Code cave overflow at {pc:#x} (limit {limit:#x})")

    words = []
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


def is_star_trap(label):
    # r31 is the handler block in every hooked site; [r31 + 8] is the orb ID.
    return [lwz(12, 8, 31), cmpwi(12, STAR_TRAP_ID), cond("bne", label)]


def prologue():
    return [stwu(1, -0x10, 1), mflr(0), stw(0, 0x14, 1)]


def epilogue():
    return [lwz(0, 0x14, 1), mtlr(0), addi(1, 1, 0x10), blr()]


def cave_amount():
    # Replaces `bl fn_8015C770` (victim coins). The caller computes (n + 1) / 2,
    # so returning min(stars, 1) yields 1 with a Star and 0 without.
    return (
        is_star_trap("amount_vanilla") + prologue()
        + [branch(FN_STAR_GET, link=True), cmpwi(3, 1), cond("ble", "amount_done"), li(3, 1)]
        + [("label", "amount_done")] + epilogue()
        + [("label", "amount_vanilla"), branch(0x8015C770)]
    )


def cave_loss():
    # Replaces `bl fn_8017E03C` (victim loses coins).
    return (
        is_star_trap("loss_vanilla") + [cmpwi(27, 0), beqlr()] + prologue()
        + [lwz(3, 0, 31), branch(FN_STATUS_SHOW, link=True)]
        + [lwz(3, 0, 31), li(4, -1), branch(FN_STAR_POPUP, link=True), branch("loss_check")]
        + [("label", "loss_wait"), branch(FN_YIELD, link=True)]
        + [("label", "loss_check"), lwz(3, 0, 31), branch(FN_STAR_POPUP_DONE, link=True)]
        + [cmpwi(3, 0), cond("beq", "loss_wait")]
        + [lwz(3, 0, 31), li(4, -1), branch(FN_STAR_ADD, link=True)]
        + epilogue()
        + [("label", "loss_vanilla"), branch(0x8017E03C)]
    )


def cave_loss_icon():
    # Replaces `bl fn_801E705C` (victim coin popup): the Star popup is shown by cave_loss.
    return [lwz(12, 8, 31), cmpwi(12, STAR_TRAP_ID), beqlr(), branch(0x801E705C)]


def cave_message():
    # Replaces both `bl fn_8016B36C` calls. r4 is 0x360004 (taken) or 0x360005 (none).
    return (
        is_star_trap("message_vanilla")
        + [addi(4, 4, EVENT_TAKEN - 4)]
        + [("label", "message_vanilla"), branch(0x8016B36C)]
    )


def cave_reward():
    # Replaces `bl fn_801E26E8` (coins fly to the owner).
    return (
        is_star_trap("reward_vanilla")
        + [lwz(4, 4, 31), cmpwi(4, 0), cond("blt", "reward_skip"), cmpwi(4, 4), cond("bge", "reward_skip")]
        + prologue()
        + [lwz(3, 4, 31), li(4, 1), branch(FN_STAR_ADD, link=True)]
        + [lwz(3, 4, 31), branch(FN_STATUS_SHOW, link=True)]
        + [lwz(3, 4, 31), li(4, 1), branch(FN_STAR_POPUP, link=True), branch("reward_check")]
        + [("label", "reward_wait"), branch(FN_YIELD, link=True)]
        + [("label", "reward_check"), lwz(3, 4, 31), branch(FN_STAR_POPUP_DONE, link=True)]
        + [cmpwi(3, 0), cond("beq", "reward_wait")]
        + epilogue()
        + [("label", "reward_skip"), blr()]
        + [("label", "reward_vanilla"), branch(0x801E26E8)]
    )


def cave_ai():
    # Runs at the start of mbCapComChanceGet (the CPU's "how much do I want this orb" lookup).
    # The AI table has no record for the Star Trap, so the CPU would never use, place or
    # keep it; look it up as Piranha Plant instead. Replaces `mr r20, r3` (r20 = orb ID).
    return (
        [cmpwi(3, STAR_TRAP_ID), cond("bne", "ai_done"), li(3, PIRANHA_ID)]
        + [("label", "ai_done"), mr(20, 3), branch(0x801C93A4)]
    )


def cave_list():
    # Runs at the end of mbCapListRead, before the -1 terminator is written (r28 = entries
    # copied so far, the list is at LIST_BUFFER). Appends the Star Trap entry with no price
    # override (falls back to the capsuleData price); see STAR_TRAP_ODDS for its weights.
    buffer_high = LIST_BUFFER + 0x8000 >> 16
    buffer_low = LIST_BUFFER - (buffer_high << 16)
    items = [cmpwi(28, LIST_MAX_ENTRIES), cond("bge", "list_done")]
    if STAR_TRAP_ODDS == "average":
        items += [cmpwi(28, STAR_TRAP_MIN_LIST), cond("blt", "list_done")]
    items += [lis(3, buffer_high), addi(3, 3, buffer_low)]
    items += [slwi(6, 28, 4), add(6, 3, 6)]
    items += [li(7, STAR_TRAP_ID), stb(7, 0, 6), li(7, 0), stb(7, 1, 6), stb(7, 2, 6), stb(7, 3, 6)]
    items += [li(8, 4)]
    items += [("label", "list_byte")]
    if STAR_TRAP_ODDS == "average":
        # r9 = sum of the non-zero weights at byte r8, r10 = how many; weight = rounded mean.
        items += [li(9, 0), li(10, 0), li(4, 0)]
        items += [("label", "list_entry"), cmpw(4, 28), cond("bge", "list_mean")]
        items += [slwi(5, 4, 4), add(5, 5, 8), lbzx(11, 3, 5), cmpwi(11, 0), cond("ble", "list_next")]
        items += [add(9, 9, 11), addi(10, 10, 1)]
        items += [("label", "list_next"), addi(4, 4, 1), branch("list_entry")]
        items += [("label", "list_mean"), li(7, 0), cmpwi(10, 0), cond("beq", "list_store")]
        items += [srwi(7, 10, 1), add(7, 9, 7), divw(7, 7, 10)]
    else:
        items += [li(7, STAR_TRAP_TEST_WEIGHT)]
    items += [("label", "list_store"), stbx(7, 6, 8), addi(8, 8, 1), cmpwi(8, 16)]
    items += [cond("blt", "list_byte"), addi(28, 28, 1)]
    items += [("label", "list_done"), li(5, -1), branch(0x801C8020)]
    return items


# Each region holds the listed caves back to back; the hook table below refers to labels.
CAVES = {
    "a": (cave_amount, cave_loss_icon, cave_message, cave_ai),
    "b": (cave_loss,),
    "c": (cave_reward,),
    "d": (cave_list,),
}
CAVE_ENTRY = {
    "amount": ("a", 0),
    "icon": ("a", 1),
    "message": ("a", 2),
    "ai": ("a", 3),
    "loss": ("b", 0),
    "reward": ("c", 0),
    "list": ("d", 0),
}

# address: (vanilla word, cave name, link)
HOOKS = {
    0x801A4720: (encode_branch(0x801A4720, 0x8015C770, True), "amount", True),
    0x801A4878: (encode_branch(0x801A4878, 0x8017E03C, True), "loss", True),
    0x801A4970: (encode_branch(0x801A4970, 0x801E705C, True), "icon", True),
    0x801A498C: (encode_branch(0x801A498C, 0x8016B36C, True), "message", True),
    0x801A49A4: (encode_branch(0x801A49A4, 0x8016B36C, True), "message", True),
    0x801A4A1C: (encode_branch(0x801A4A1C, 0x801E26E8, True), "reward", True),
    0x801C801C: (0x38A0FFFF, "list", False),
    0x801C93A0: (mr(20, 3)[1], "ai", False),
}
VANILLA_TEXT = {
    0x801A4720: "bl fn_8015C770",
    0x801A4878: "bl fn_8017E03C",
    0x801A4970: "bl fn_801E705C",
    0x801A498C: "bl fn_8016B36C",
    0x801A49A4: "bl fn_8016B36C",
    0x801A4A1C: "bl fn_801E26E8",
    0x801C801C: "li r5, -0x1",
}


def build_caves():
    words = []
    entries = {}
    for region, builders in CAVES.items():
        base, limit = REGIONS[region]
        items = []
        # Entry address of each cave is the pc before its first item.
        offsets = []
        count = 0
        for builder in builders:
            offsets.append(count)
            built = builder()
            items.extend(built)
            count += sum(1 for item in built if item[0] != "label")
        region_words, _ = assemble(base, items, limit)
        words.extend(region_words)
        for index, offset in enumerate(offsets):
            for name, (entry_region, entry_index) in CAVE_ENTRY.items():
                if entry_region == region and entry_index == index:
                    entries[name] = base + 4 * offset
    return words, entries


def obj_block(text, name):
    start = text.index(f".obj {name}, global")
    end = text.index(f".endobj {name}", start)
    return start, end


def patch_obj_words(text, name, index, values):
    """values: list of (asm_text, word) for each word; asm_text None keeps the line."""
    start, end = obj_block(text, name)
    lines = text[start:end].splitlines(keepends=True)
    data_lines = [i for i, line in enumerate(lines) if line.lstrip().startswith(".4byte")]
    for offset, (asm_text, _) in enumerate(values):
        if asm_text is None:
            continue
        line_index = data_lines[index + offset]
        prefix = lines[line_index][: lines[line_index].index(".4byte")]
        newline = "\r\n" if lines[line_index].endswith("\r\n") else "\n"
        lines[line_index] = f"{prefix}.4byte {asm_text}{newline}"
    return text[:start] + "".join(lines) + text[end:]


def read_obj_words(text, name, index, count):
    start, end = obj_block(text, name)
    lines = [line.strip() for line in text[start:end].splitlines() if line.strip().startswith(".4byte")]
    return [line.split(None, 1)[1].strip() for line in lines[index:index + count]]


CAPSULE_ROW = CAPSULE_DATA_ROW_WORDS * STAR_TRAP_ID
CAPSULE_VANILLA = [
    "0x00000000", "0x00000000", "0x00000000", "0x00380022", "0x0000000A",
    "0x00000000", "0x00000000", "0x5A000000", "lbl_802DD69D", "0x00000000",
]
CAPSULE_NEW = [
    (f"0x{STAR_TRAP_MODEL:08X}", STAR_TRAP_MODEL),
    (f"0x{STAR_TRAP_FRAME:08X}", STAR_TRAP_FRAME),
    (f"0x0037{DESC_MESSAGE:04X}", 0x00370000 | DESC_MESSAGE),
    (f"0x0038{NAME_MESSAGE:04X}", 0x00380000 | NAME_MESSAGE),
    ("0x00000001", 1),
    (f"0x{STAR_TRAP_COLOUR:08X}", STAR_TRAP_COLOUR),
    (f"0x{STAR_TRAP_PRICE:08X}", STAR_TRAP_PRICE),
    (f"0x{STAR_TRAP_RARITY:02X}000001", STAR_TRAP_RARITY << 24 | 1),
    (None, None),
    ("0x01000000", 0x01000000),
]
EVENT_ROW = EVENT_TABLE_ROW_WORDS * STAR_TRAP_ID
EVENT_VANILLA = [
    "0x00000000", "0x00000000", "0x00000000", "0x00000000",
    "0x00000001", "0xFFFFFFFF", "0x00000000",
]
EVENT_NEW = [
    ("fn_801A3BC8", 0x801A3BC8),
    ("fn_801A4A70", 0x801A4A70),
    ("0x00000000", 0),
    ("0x00000001", 1),
    ("0x00000002", 2),
    ("0x00170000", 0x00170000),
    ("0x00000000", 0),
]


CAPSULE_TUNABLE = {0, 1, 5, 6, 7}  # model, frame, colour, price, rarity: may hold values from an earlier run


def check_rows(text, name, row, vanilla, new, tunable=()):
    current = read_obj_words(text, name, row, len(vanilla))
    wanted = [asm if asm is not None else vanilla[i] for i, (asm, _) in enumerate(new)]
    patched = all(
        current[i] == wanted[i] for i in range(len(wanted)) if i not in tunable
    )
    if current != vanilla and not patched:
        raise RuntimeError(f"Unexpected {name} row {row // len(vanilla)}: {current!r}")


def patch_dol_rows(dol, table_address, row, new):
    base = dol_offset(dol, table_address + 4 * row)
    for offset, (asm, word) in enumerate(new):
        if asm is not None:
            struct.pack_into(">I", dol, base + 4 * offset, word)


def build_messages():
    outputs = {}
    for name in MESS_NAMES:
        # The English file chains onto earlier patches; the others start from the original.
        chained = MESS_OUTPUT_DIR / name
        source = chained if name == MESS_OUTPUT.name and chained.exists() else MESS_SOURCE_DIR / name
        outputs[name] = append_records(source.read_bytes(), MESSAGE_ADDITIONS, name)
    return outputs


def capsule_entries(data):
    count = struct.unpack_from(">I", data, 0)[0]
    offsets = [struct.unpack_from(">I", data, 4 + 4 * i)[0] for i in range(count)] + [len(data)]
    return [data[offsets[i]:offsets[i + 1]] for i in range(count)]


def pack_capsule(entries):
    """Rebuild the archive: count, absolute offsets, then entries padded to even offsets."""
    offset = 4 + 4 * len(entries)
    table = []
    body = b""
    for entry in entries:
        table.append(offset)
        entry += b"\x00" * (len(entry) % 2)
        body += entry
        offset += len(entry)
    return struct.pack(f">I{len(entries)}I", len(entries), *table) + body


def compress_entry(model):
    packed = zlib.compress(model, 9)
    return struct.pack(">IIII", len(model), 7, len(model), len(packed)) + packed


def build_capsule():
    source = CAPSULE_SOURCE.read_bytes()
    entries = capsule_entries(source)
    if len(entries) != 85:
        raise RuntimeError(f"Unexpected capsule.bin entry count: {len(entries)}")
    if pack_capsule(entries) != source:
        raise RuntimeError("capsule.bin does not rebuild byte-for-byte; layout assumption is wrong")
    for name in CAPSULE_NEW_ENTRIES:
        entries.append(compress_entry((ASSETS / name).read_bytes()))
    return pack_capsule(entries)


def main():
    text_asm = ASM_TEXT.read_bytes().decode("utf-8")
    data_asm = ASM_DATA.read_bytes().decode("utf-8")
    init_asm = ASM_INIT.read_bytes().decode("utf-8")
    dol = bytearray(DOL.read_bytes())

    check_rows(data_asm, CAPSULE_DATA, CAPSULE_ROW, CAPSULE_VANILLA, CAPSULE_NEW, CAPSULE_TUNABLE)
    check_rows(data_asm, EVENT_TABLE, EVENT_ROW, EVENT_VANILLA, EVENT_NEW)
    data_asm = patch_obj_words(data_asm, CAPSULE_DATA, CAPSULE_ROW, CAPSULE_NEW)
    data_asm = patch_obj_words(data_asm, EVENT_TABLE, EVENT_ROW, EVENT_NEW)
    patch_dol_rows(dol, 0x80266BDC, CAPSULE_ROW, CAPSULE_NEW)
    patch_dol_rows(dol, 0x80268500, EVENT_ROW, EVENT_NEW)

    cave_words, entries = build_caves()
    for address, word, mnemonic in cave_words:
        init_asm = patch_asm_word(init_asm, address, word, mnemonic, allowed=None)
        struct.pack_into(">I", dol, dol_offset(dol, address), word)

    for address, (vanilla, cave, link) in HOOKS.items():
        position = dol_offset(dol, address)
        found = struct.unpack_from(">I", dol, position)[0]
        target = entries[cave]
        patched = encode_branch(address, target, link)
        if found not in (vanilla, patched):
            raise RuntimeError(f"Unexpected word at {address:08X}: {found:08X}")
        struct.pack_into(">I", dol, position, patched)
        mnemonic = f"b{'l' if link else ''} 0x{target:08X}"
        text_asm = patch_text_word(text_asm, address, patched, mnemonic)

    messages = build_messages()
    capsule = build_capsule()

    ASM_TEXT.write_bytes(text_asm.encode("utf-8"))
    ASM_DATA.write_bytes(data_asm.encode("utf-8"))
    ASM_INIT.write_bytes(init_asm.encode("utf-8"))
    DOL.write_bytes(dol)
    MESS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in messages.items():
        (MESS_OUTPUT_DIR / name).write_bytes(data)
    print(f"Patched Star Trap Orb (ID {STAR_TRAP_ID}): hit orb, steals 1 Star on landing")
    for name, address in sorted(entries.items(), key=lambda item: item[1]):
        print(f"  cave {name}: {address:#010x}")
    CAPSULE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    CAPSULE_OUTPUT.write_bytes(capsule)
    print(f"Built message files in {MESS_OUTPUT_DIR}")
    print(f"Built {CAPSULE_OUTPUT} ({len(CAPSULE_NEW_ENTRIES)} new model entries)")


if __name__ == "__main__":
    main()
