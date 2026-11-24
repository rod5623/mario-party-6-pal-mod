"""DOL access and safe byte patching: address -> file offset, branches, asm-listing edits."""
import re
import struct


def encode_branch(source, target, link=False):
    displacement = target - source
    if displacement % 4 or not -(1 << 25) <= displacement < (1 << 25):
        raise ValueError(f"Branch out of range: {source:#x} -> {target:#x}")
    return 0x48000000 | (displacement & 0x03FFFFFC) | int(link)


def dol_offset(dol, address):
    for offset_pos, address_pos, size_pos, count in (
        (0x00, 0x48, 0x90, 7),
        (0x1C, 0x64, 0xAC, 11),
    ):
        for index in range(count):
            file_offset = struct.unpack_from(">I", dol, offset_pos + 4 * index)[0]
            section_address = struct.unpack_from(">I", dol, address_pos + 4 * index)[0]
            section_size = struct.unpack_from(">I", dol, size_pos + 4 * index)[0]
            if section_size and section_address <= address < section_address + section_size:
                return file_offset + address - section_address
    raise ValueError(f"Address {address:#010x} is not in a DOL section")


def replace_bytes(data, offset, original, patched, description):
    actual = bytes(data[offset:offset + len(original)])
    if actual == original:
        data[offset:offset + len(patched)] = patched
    elif actual != patched:
        raise RuntimeError(
            f"Unexpected {description}: expected {original.hex(' ')}, "
            f"found {actual.hex(' ')}"
        )


def patch_dol_instruction(dol, address, original, patched, description):
    replace_bytes(dol, dol_offset(dol, address), original, patched, description)


def patch_asm_instruction(text, address, original, patched, old_asm, new_asm):
    lines = text.splitlines(keepends=True)
    matching = [i for i, line in enumerate(lines) if f"/* {address:08X} " in line]
    if len(matching) != 1:
        raise RuntimeError(f"Expected one instruction at {address:08X}, found {len(matching)}")

    index = matching[0]
    line = lines[index]
    old_hex = original.hex(" ").upper()
    new_hex = patched.hex(" ").upper()
    if old_hex in line and old_asm in line:
        lines[index] = line.replace(old_hex, new_hex, 1).replace(old_asm, new_asm, 1)
    elif new_hex in line and new_asm in line:
        pass
    else:
        raise RuntimeError(f"Unexpected assembly at {address:08X}: {line.strip()}")
    return "".join(lines)


def patch_asm_word(text, address, word, mnemonic, allowed=()):
    lines = text.splitlines(keepends=True)
    matching = [i for i, line in enumerate(lines) if f"/* {address:08X} " in line]
    if len(matching) != 1:
        raise RuntimeError(f"Expected one code-cave word at {address:08X}, found {len(matching)}")

    index = matching[0]
    line = lines[index]
    prefix, separator, remainder = line.partition("*/")
    if not separator:
        raise RuntimeError(f"Malformed assembly at {address:08X}: {line.strip()}")

    byte_match = re.search(
        r"((?:[0-9A-F]{2} ){3}[0-9A-F]{2}|[0-9A-F]{8})\s*$", prefix
    )
    word_match = re.search(r"\.4byte 0x([0-9A-F]{8}) /\* [^*]+ \*/", remainder)
    if not byte_match or not word_match:
        raise RuntimeError(f"Unexpected code-cave assembly at {address:08X}: {line.strip()}")

    current = int(word_match.group(1), 16)
    if allowed is not None and current not in (0, word, *allowed):
        raise RuntimeError(f"Unexpected code-cave word at {address:08X}: {current:08X}")

    encoded = struct.pack(">I", word).hex(" ").upper()
    prefix = prefix[:byte_match.start(1)] + encoded + " "
    remainder = re.sub(
        r"\.4byte 0x[0-9A-F]{8} /\* [^*]+ \*/",
        f".4byte 0x{word:08X} /* {mnemonic} */",
        remainder,
        count=1,
    )
    lines[index] = prefix + separator + remainder
    return "".join(lines)


def patch_word_table(text, start_marker, end_marker, original, patched):
    start = text.index(start_marker)
    end = text.index(end_marker, start) + len(end_marker)
    block = text[start:end]
    values = re.findall(r"^\s*\.4byte 0x([0-9A-Fa-f]{8})\s*$", block, re.MULTILINE)
    current = [int(value, 16) for value in values]
    if current == original:
        replacement = patched
    elif current == patched:
        return text
    else:
        raise RuntimeError(f"Unexpected data table {start_marker}: {current!r}")

    iterator = iter(replacement)
    block = re.sub(
        r"(^\s*\.4byte )0x[0-9A-Fa-f]{8}(\s*$)",
        lambda match: f"{match.group(1)}0x{next(iterator):08X}{match.group(2)}",
        block,
        flags=re.MULTILINE,
    )
    return text[:start] + block + text[end:]


def write_cave(dol, address, code):
    position = dol_offset(dol, address)
    current = bytes(dol[position:position + len(code)])
    if current not in (b"\0" * len(code), code):
        raise RuntimeError(f"Code cave {address:#010x} is not free")
    dol[position:position + len(code)] = code
