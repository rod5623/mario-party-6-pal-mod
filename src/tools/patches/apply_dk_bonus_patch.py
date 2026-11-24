"""New DK Bonus wheel faces: python -m tools.patches.apply_dk_bonus_patch

Faces: 5 = +1 Star, 10 = +2 Stars, 20 = lose up to 30 coins, 30 = +50 coins, Star = -1 Star
(if the player has one).

- Result table lbl_80266A9C (DK_RESULT_TABLE) gets NEW_RESULTS. Faces 5, 10 and Star take the
  vanilla Star branch; face 20 is rewritten at run time to -min(30, coins).
- Code caves in the init section: 0x800036E8-0x80003748 (result hook) and 0x80003750-0x800037E4
  (helpers). 0x80003748 holds an unrelated blr. Every word of both caves is rewritten, which
  clears what earlier versions of this patch left there.
- Hooks (HOOKS): 0x801BC6D0, 0x801BC6E4, 0x801BC6F4, 0x801BC87C, 0x801BC898 and 0x801BC8C4
  branch into the caves; the other HOOKS addresses are restored to vanilla.
- Message bank 0x3E (English): records 11 (no Star to take) and 12 (coin loss) are added to the
  vanilla 11. The bank is built from the pristine file and spliced in with write_bank, so other
  banks in the current output are kept.

Writes main.dol, the .text, .data and init listings, and files/mess/messdata_eng.bin. No
prerequisites. Other patches import its small encoders (assemble, branch, patch_text_word).
Idempotent; accepts the words of earlier versions (PREVIOUS_RESULTS, PREVIOUS_WORDS).
"""
import re
import struct

from tools.lib.messages import write_bank

from tools.lib.paths import ASM_DATA, ASM_INIT, ASM_TEXT, DOL, MESS_OUTPUT, MESS_SOURCE
from tools.lib.dol import dol_offset, encode_branch, patch_asm_word

DK_RESULT_TABLE = 0x80266A9C
DK_MESSAGE_BANK = 0x3E
DK_ORIGINAL_MESSAGE_COUNT = 11
DK_NO_STAR_MESSAGE_ID = 11
DK_COIN_LOSS_MESSAGE_ID = 12

# Code-cave regions owned by the DK patch. 0x80003748 holds an unrelated blr.
CAVE_RESULT = 0x800036E8
CAVE_RESULT_END = 0x80003748
CAVE_HELPERS = 0x80003750
CAVE_HELPERS_END = 0x800037E4

ORIGINAL_RESULTS = [5, 10, 20, 30, 0xFFFFFFFF]
PREVIOUS_RESULTS = [0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFE2, 50, 0xFFFFFFFF]
# Faces 5, 10 and Star take the vanilla Star branch (negative). Face 20 is
# overwritten at runtime with -min(30, coins) and handled by the coin branch.
NEW_RESULTS = [0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFE2, 50, 0xFFFFFFFF]

# address: (vanilla word, vanilla asm text)
HOOKS = {
    0x801BC6D0: (0x418001D0, "blt .L_801BC8A0"),
    0x801BC6E4: (0x7CA5002E, "lwzx r5, r5, r0"),
    0x801BC6F4: (0x38840003, "addi r4, r4, 0x3"),
    0x801BC87C: (0x4BFC17C1, "bl fn_8017E03C"),
    0x801BC898: (0x4802A7C5, "bl fn_801E705C"),
    0x801BC8A8: (0x38840004, "addi r4, r4, 0x4"),
    0x801BC8B8: (0x38600000, "li r3, 0x0"),
    0x801BC8C0: (0x38A0FFFF, "li r5, -0x1"),
    0x801BC8C4: (0x4BFB190D, "bl fn_8016E1D0"),
    0x801BC8C8: (0x7FA3EB78, "mr r3, r29"),
    0x801BC8CC: (0x4BFC998D, "bl fn_80186258"),
    0x801BC8D4: (0x4BFB35B1, "bl fn_8016FE84"),
}
PREVIOUS_WORDS = {
    0x801BC8A8: {0x38840007},
    0x801BC8B8: {0x7FA3EB78},
    0x801BC8C4: {0x48000004},
    0x801BC8C8: {0x2C150004},
    0x801BC8CC: {0x4182000C},
}
TEXT_FILE_OFFSET = 0x80003260  # address - listing offset in the .text asm


def cmpwi(reg, imm):
    return f"cmpwi r{reg}, {imm:#x}", 0x2C000000 | reg << 16 | imm & 0xFFFF


def li(reg, imm):
    text = f"li r{reg}, {imm:#x}" if imm >= 0 else f"li r{reg}, -{-imm:#x}"
    return text, 0x38000000 | reg << 21 | imm & 0xFFFF


def addi(rd, ra, imm):
    return f"addi r{rd}, r{ra}, {imm:#x}", 0x38000000 | rd << 21 | ra << 16 | imm & 0xFFFF


def mr(ra, rs):
    return f"mr r{ra}, r{rs}", 0x7C000378 | rs << 21 | ra << 16 | rs << 11


def neg(rd, ra):
    return f"neg r{rd}, r{ra}", 0x7C0000D0 | rd << 21 | ra << 16


def slwi2(ra, rs):
    return f"slwi r{ra}, r{rs}, 2", 0x5400103A | rs << 21 | ra << 16


def stwx(rs, ra, rb):
    return f"stwx r{rs}, r{ra}, r{rb}", 0x7C00012E | rs << 21 | ra << 16 | rb << 11


def lwzx(rd, ra, rb):
    return f"lwzx r{rd}, r{ra}, r{rb}", 0x7C00002E | rd << 21 | ra << 16 | rb << 11


def mflr(reg):
    return f"mflr r{reg}", 0x7C0802A6 | reg << 21


def mtlr(reg):
    return f"mtlr r{reg}", 0x7C0803A6 | reg << 21


def beqlr():
    return "beqlr", 0x4D820020


def branch(target, link=False):
    return ("b", target, link)


def cond(mnemonic, target):
    opcode = {"beq": 0x41820000, "bne": 0x40820000, "bge": 0x40800000, "ble": 0x40810000}
    return (mnemonic, target, opcode[mnemonic])


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
        elif item[0] in ("beq", "bne", "bge", "ble"):
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


def result_hook():
    return [
        cmpwi(21, 2), cond("beq", "face20"),
        cmpwi(21, 4), cond("beq", "star_face"),
        cmpwi(0, 0), cond("bge", "positive"),
        branch(0x801BC8A0),
        # Star face: slot = -Stars (0 with none); coin_effect then takes one Star.
        ("label", "star_face"), mflr(31), mr(3, 29),
        branch(0x8015CE98, link=True), mtlr(31), branch("negate"),
        ("label", "face20"), mflr(31), mr(3, 29),
        branch(0x8015C770, link=True), mtlr(31),
        cmpwi(3, 30), cond("ble", "negate"), li(3, 30),
        ("label", "negate"), neg(3, 3),
        slwi2(0, 21), addi(4, 30, 0x4DC), stwx(3, 4, 0),
        ("label", "positive"), branch(0x801BC6D4),
    ]


def helper_code():
    return [
        ("label", "format"), lwzx(5, 5, 0), cmpwi(5, 0), cond("bge", "format_done"),
        neg(5, 5),
        ("label", "format_done"), branch(0x801BC6E8),
        ("label", "message"), addi(4, 4, 3), cmpwi(21, 2), cond("bne", "not20"),
        addi(4, 4, DK_COIN_LOSS_MESSAGE_ID - 3),
        ("label", "not20"), cmpwi(21, 4), cond("bne", "message_done"),
        addi(4, 4, DK_NO_STAR_MESSAGE_ID - 3),
        ("label", "message_done"), branch(0x801BC6F8),
        # Star face: r3 = player, r4 = -Stars; take one Star (tail call), or nothing.
        ("label", "coin_effect"), cmpwi(21, 4), cond("bne", "coin_normal"),
        cmpwi(4, 0), beqlr(), li(4, -1), branch(0x8015CF64),
        ("label", "coin_normal"), branch(0x8017E03C),
        ("label", "coin_icon"), cmpwi(21, 4), beqlr(), branch(0x801E705C),
        ("label", "star"), cmpwi(21, 1), cond("bne", "star_done"),
        mflr(31), mr(3, 29), branch(0x8003D028, link=True), addi(4, 3, 1),
        mr(3, 29), branch(0x8003CF28, link=True), mtlr(31),
        li(3, 0), li(4, 1), li(5, -1),
        ("label", "star_done"), branch(0x8016E1D0),
    ]


def patch_text_word(text, address, word, mnemonic):
    lines = text.splitlines(keepends=True)
    encoded = struct.pack(">I", word).hex(" ").upper()
    pattern = re.compile(
        rf"^(/\* {address:08X} [0-9A-F]{{8}}  )[0-9A-F ]{{11}}( \*/\t).*?(\r?\n?)$"
    )
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            lines[index] = f"{match.group(1)}{encoded}{match.group(2)}{mnemonic}{match.group(3)}"
            return "".join(lines)

    previous = [i for i, line in enumerate(lines) if f"/* {address - 4:08X} " in line]
    if len(previous) != 1:
        raise RuntimeError(f"Cannot locate assembly line near {address:08X}")
    newline = "\r\n" if lines[previous[0]].endswith("\r\n") else "\n"
    lines.insert(
        previous[0] + 1,
        f"/* {address:08X} {address - TEXT_FILE_OFFSET:08X}  {encoded} */\t{mnemonic}{newline}",
    )
    return "".join(lines)


def patch_data_table(text):
    marker = ".obj lbl_80266A6C, global"
    start = text.index(marker)
    end = text.index(".endobj lbl_80266A6C", start)
    block = text[start:end]
    lines = block.splitlines(keepends=True)
    value_lines = [
        i for i, line in enumerate(lines)
        if re.match(r"^\s*\.4byte 0x[0-9A-Fa-f]{8}\s*$", line)
    ]
    offset = (DK_RESULT_TABLE - 0x80266A6C) // 4
    selected = value_lines[offset:offset + 5]
    current = [int(re.search(r"0x([0-9A-Fa-f]{8})", lines[i]).group(1), 16) for i in selected]
    if current not in (ORIGINAL_RESULTS, PREVIOUS_RESULTS, NEW_RESULTS):
        raise RuntimeError(f"Unexpected DK result table: {current!r}")
    for index, value in zip(selected, NEW_RESULTS):
        lines[index] = re.sub(r"0x[0-9A-Fa-f]{8}", f"0x{value:08X}", lines[index])
    return text[:start] + "".join(lines) + text[end:]


def build_messages():
    data = bytearray(MESS_SOURCE.read_bytes())
    section_count = struct.unpack_from(">I", data, 0)[0]
    if section_count <= DK_MESSAGE_BANK + 1:
        raise RuntimeError(f"Unexpected message section count: {section_count}")

    def section_start(index):
        relative = struct.unpack_from(">I", data, 4 + 4 * index)[0]
        return 4 + relative

    base = section_start(DK_MESSAGE_BANK)
    end = section_start(DK_MESSAGE_BANK + 1)
    count = struct.unpack_from(">I", data, base)[0]
    if count != DK_ORIGINAL_MESSAGE_COUNT:
        raise RuntimeError(f"Unexpected DK message count: {count}")

    offsets = [
        struct.unpack_from(">I", data, base + 4 + 4 * index)[0]
        for index in range(count)
    ]
    bounds = [base + 4 + offset for offset in offsets] + [end]
    records = [
        bytes(data[bounds[index]:bounds[index + 1]])
        for index in range(count)
    ]

    for message in (
        b"\x00\x15\x00\x03Sorry,\x10not\x10this\x10time,\x10pal!\xc2\xff\x00",
        b"\x00\x15\x00\x03DK\x10takes\x10\x19\x01\x10coin!\xc2\xff\x00",
    ):
        records.append(message + b"\0" * (-len(message) % 4))
    if len(records) != DK_COIN_LOSS_MESSAGE_ID + 1:
        raise RuntimeError("Unexpected DK message ids")

    table_size = 4 + 4 * len(records)
    position = table_size
    new_offsets = []
    for record in records:
        new_offsets.append(position - 4)
        position += len(record)

    block = struct.pack(">I", len(records))
    block += struct.pack(f">{len(records)}I", *new_offsets)
    block += b"".join(records)
    delta = len(block) - (end - base)
    if delta <= 0:
        raise RuntimeError("DK message block did not grow as expected")

    data[base:end] = block
    for index in range(DK_MESSAGE_BANK + 1, section_count):
        offset_position = 4 + 4 * index
        old_offset = struct.unpack_from(">I", data, offset_position)[0]
        struct.pack_into(">I", data, offset_position, old_offset + delta)
    return data


def is_cave_branch(address, word):
    if word >> 26 != 0x12 or word & 2:
        return False
    displacement = word & 0x03FFFFFC
    if displacement & 0x02000000:
        displacement -= 0x04000000
    return 0x80003600 <= address + displacement < 0x80003900


def main():
    text_asm = ASM_TEXT.read_bytes().decode("utf-8")
    data_asm = ASM_DATA.read_bytes().decode("utf-8")
    init_asm = ASM_INIT.read_bytes().decode("utf-8")
    dol = bytearray(DOL.read_bytes())

    data_asm = patch_data_table(data_asm)
    offset = dol_offset(dol, DK_RESULT_TABLE)
    current = list(struct.unpack_from(">5I", dol, offset))
    if current not in (ORIGINAL_RESULTS, PREVIOUS_RESULTS, NEW_RESULTS):
        raise RuntimeError(f"Unexpected DK result table bytes: {current!r}")
    struct.pack_into(">5I", dol, offset, *NEW_RESULTS)

    result_words, _ = assemble(CAVE_RESULT, result_hook(), CAVE_RESULT_END)
    helper_words, labels = assemble(CAVE_HELPERS, helper_code(), CAVE_HELPERS_END)
    cave = {address: (word, text) for address, word, text in result_words + helper_words}

    # Clear every word owned by earlier DK patch versions, then write new code.
    for start, end in ((CAVE_RESULT, CAVE_RESULT_END), (CAVE_HELPERS, CAVE_HELPERS_END)):
        for address in range(start, end, 4):
            word, mnemonic = cave.get(address, (0, "invalid"))
            init_asm = patch_asm_word(init_asm, address, word, mnemonic, allowed=None)
            struct.pack_into(">I", dol, dol_offset(dol, address), word)

    targets = {
        0x801BC6D0: branch(CAVE_RESULT),
        0x801BC6E4: branch(labels["format"]),
        0x801BC6F4: branch(labels["message"]),
        0x801BC87C: branch(labels["coin_effect"], link=True),
        0x801BC898: branch(labels["coin_icon"], link=True),
        0x801BC8C4: branch(labels["star"], link=True),
    }
    for address, (vanilla, vanilla_text) in HOOKS.items():
        position = dol_offset(dol, address)
        found = struct.unpack_from(">I", dol, position)[0]
        if found != vanilla and found not in PREVIOUS_WORDS.get(address, ()) \
                and not is_cave_branch(address, found):
            raise RuntimeError(f"Unexpected word at {address:08X}: {found:08X}")
        if address in targets:
            _, target, link = targets[address]
            word = encode_branch(address, target, link)
            mnemonic = f"b{'l' if link else ''} 0x{target:08X}"
        else:
            word, mnemonic = vanilla, vanilla_text
        struct.pack_into(">I", dol, position, word)
        text_asm = patch_text_word(text_asm, address, word, mnemonic)

    message_output = build_messages()
    ASM_TEXT.write_bytes(text_asm.encode("utf-8"))
    ASM_DATA.write_bytes(data_asm.encode("utf-8"))
    ASM_INIT.write_bytes(init_asm.encode("utf-8"))
    DOL.write_bytes(dol)
    write_bank(MESS_OUTPUT, MESS_SOURCE, message_output, DK_MESSAGE_BANK)
    print("Patched DK Bonus: 5=+1 Star, 10=+2 Stars, 20=-up-to-30 coins, 30=+50 coins, Star=-1 Star (if any)")
    print(f"Built English message file: {MESS_OUTPUT}")


if __name__ == "__main__":
    main()
