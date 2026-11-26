"""REL relocation tools: read module-0 relocations, add calls into DOL code, retarget them."""
import struct


def text_base(rel):
    """File offset of REL section 1 (.text)."""
    section_table = struct.unpack_from(">I", rel, 0x10)[0]
    offset = struct.unpack_from(">I", rel, section_table + 8)[0] & ~1
    if not offset:
        raise RuntimeError("REL has no section 1")
    return offset


def walk_relocs(rel, offset):
    """Yield (record_position, section, text_offset, kind, target_section, addend)."""
    position = offset
    section = 0
    cursor = 0
    while True:
        delta, kind, target, addend = struct.unpack_from(">HBBI", rel, position)
        if kind == R_DOLPHIN_END:
            return
        if kind == R_DOLPHIN_SECTION:
            section, cursor = target, 0
        else:
            cursor += delta
            yield position, section, cursor, kind, target, addend
        position += 8


def import_blocks(rel):
    imp_offset, imp_size = struct.unpack_from(">II", rel, 0x28)
    return {
        struct.unpack_from(">I", rel, imp_offset + 8 * i)[0]: struct.unpack_from(">I", rel, imp_offset + 8 * i + 4)[0]
        for i in range(imp_size // 8)
    }


def retarget_call(rel, text_offset, old_target, new_target):
    """Change the DOL address of an existing module-0 relocation at a text offset."""
    block = import_blocks(rel)[0]
    for position, section, cursor, kind, _, addend in walk_relocs(rel, block):
        if section == 1 and cursor == text_offset and kind == R_PPC_REL24:
            if addend == new_target:
                return False
            if addend != old_target:
                raise RuntimeError(f"Relocation at {text_offset:#x} targets {addend:#x}, expected {old_target:#x}")
            struct.pack_into(">I", rel, position + 4, new_target)
            return True
    raise RuntimeError(f"No module-0 REL24 relocation at text offset {text_offset:#x}")


def add_calls(rel, sites):
    """Append module-0 REL24 relocations: sites = [(text_offset, dol_target), ...].

    The instruction at each site is overwritten with a bl (the loader fills in the offset).
    Idempotent: sites that already have a module-0 relocation to the same target are skipped.
    """
    block = import_blocks(rel)[0]
    existing = {
        (cursor, addend)
        for _, section, cursor, kind, _, addend in walk_relocs(rel, block)
        if section == 1 and kind == R_PPC_REL24
    }
    pending = sorted((o, t) for o, t in sites if (o, t) not in existing)
    if not pending:
        return 0
    end = _block_end(rel, block)
    if end + 8 != len(rel):
        raise RuntimeError("Module-0 block is not at the end of the REL")
    records = struct.pack(">HBBI", 0, R_DOLPHIN_SECTION, 1, 0)
    previous = 0
    for offset, target in pending:
        position = text_base(rel) + offset
        rel[position:position + 4] = struct.pack(">I", 0x48000001)
        gap = offset - previous
        while gap > 0xFFFF:  # the delta field is 16 bits: step over long gaps with NOP records
            records += struct.pack(">HBBI", 0xFFFF, R_DOLPHIN_NOP, 0, 0)
            gap -= 0xFFFF
        records += struct.pack(">HBBI", gap, R_PPC_REL24, 4, target)
        previous = offset
    rel[end:end] = records
    return len(pending)


def _block_end(rel, offset):
    """File position of the R_DOLPHIN_END record that closes the relocation list at offset."""
    position = offset
    while struct.unpack_from(">HBBI", rel, position)[1] != R_DOLPHIN_END:
        position += 8
    return position


def check_words(rel, text_offset, *expected):
    """Raise unless the word at text_offset is one of the hex strings (original or already hooked)."""
    position = text_base(rel) + text_offset
    actual = bytes(rel[position:position + 4])
    if actual not in [bytes.fromhex(e) for e in expected]:
        raise RuntimeError(f"Unexpected word at {text_offset:#x}: {actual.hex()} (expected {expected})")

R_PPC_REL24 = 10

R_DOLPHIN_NOP = 201

R_DOLPHIN_SECTION = 202

R_DOLPHIN_END = 203
