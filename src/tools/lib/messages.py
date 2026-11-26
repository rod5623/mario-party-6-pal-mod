"""Message files (files/mess/messdata*.bin): text encoding, records, and bank edits.

messdata*.bin is a u32 bank count, then one u32 offset per bank (relative to byte 4), then the
banks. A patch that owns a single bank builds its bank from the pristine file and calls
write_bank() to put just that bank into the current output, so patches that own different banks
don't overwrite each other. Patches that share a bank append with edit_bank(). A patch that adds a
whole bank after the vanilla ones uses set_bank(); splice_bank() leaves such extra banks alone.
"""
import struct


def encode(text):
    out = bytearray()
    i = 0
    while i < len(text):
        if text.startswith("<N>", i):
            out += b"\x1f\x01"
            i += 3
            continue
        ch = text[i]
        out.append({" ": 0x10, "!": 0xC2, "?": 0xC3, "\n": 0x0A, ",": 0x82}.get(ch, ord(ch)))
        i += 1
    return bytes(out)


def record(header, body, end):
    data = bytes.fromhex(header) + body + end
    return data + b"\0" * (-len(data) % 4)

INDENT = b"\x20\x20\x20\x20"


def _bounds(data, bank):
    count = struct.unpack_from(">I", data, 0)[0]
    if not 0 <= bank < count:
        raise RuntimeError(f"Message bank {bank:#x} out of range ({count} banks)")
    start = 4 + struct.unpack_from(">I", data, 4 + 4 * bank)[0]
    end = 4 + struct.unpack_from(">I", data, 4 + 4 * (bank + 1))[0] if bank + 1 < count else len(data)
    return count, start, end


def splice_bank(target, donor, bank):
    """Return a copy of target whose bank `bank` is taken from donor.

    The target may have more banks than the donor (banks appended after the vanilla ones by set_bank),
    never fewer."""
    target = bytearray(target)
    count = struct.unpack_from(">I", target, 0)[0]
    if struct.unpack_from(">I", donor, 0)[0] > count:
        raise RuntimeError("Message files have different bank counts")
    _, t_start, t_end = _bounds(target, bank)
    _, d_start, d_end = _bounds(donor, bank)
    new = bytes(donor[d_start:d_end])
    delta = len(new) - (t_end - t_start)
    target[t_start:t_end] = new
    for index in range(bank + 1, count):
        position = 4 + 4 * index
        struct.pack_into(">I", target, position, struct.unpack_from(">I", target, position)[0] + delta)
    return target


def write_bank(output, source, donor, bank):
    """Write `output` = (the current output, else `source`) with bank `bank` taken from `donor`."""
    base = output.read_bytes() if output.exists() else source.read_bytes()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(splice_bank(base, donor, bank))


def append_records(source, additions, label):
    data = bytearray(source)
    section_count = struct.unpack_from(">I", data, 0)[0]

    def section_start(index):
        return 4 + struct.unpack_from(">I", data, 4 + 4 * index)[0]

    for bank in sorted(additions):
        original_count, new_records = additions[bank]
        base = section_start(bank)
        end = section_start(bank + 1) if bank + 1 < section_count else len(data)
        count = struct.unpack_from(">I", data, base)[0]
        offsets = [struct.unpack_from(">I", data, base + 4 + 4 * i)[0] for i in range(count)]
        bounds = [base + 4 + offset for offset in offsets] + [end]
        records = [bytes(data[bounds[i]:bounds[i + 1]]) for i in range(count)]
        if count == original_count + len(new_records):
            if records[original_count:] != new_records:
                raise RuntimeError(f"{label}: bank {bank} already has different extra records")
            continue
        if count != original_count:
            raise RuntimeError(f"{label}: unexpected record count {count} in bank {bank}")
        records.extend(new_records)

        position = 4 + 4 * len(records)
        new_offsets = []
        for record in records:
            new_offsets.append(position - 4)
            position += len(record)
        block = struct.pack(">I", len(records))
        block += struct.pack(f">{len(records)}I", *new_offsets)
        block += b"".join(records)
        delta = len(block) - (end - base)
        data[base:end] = block
        for index in range(bank + 1, section_count):
            offset_position = 4 + 4 * index
            old_offset = struct.unpack_from(">I", data, offset_position)[0]
            struct.pack_into(">I", data, offset_position, old_offset + delta)
    return data


def edit_bank(source, replacements, label, bank, bank_records, append=(), known_tails=()):
    """Return source with records of `bank` replaced and `append` added after the first bank_records.

    bank_records is how many records the bank must have before this patch's own (the vanilla count
    plus every earlier patch's appended records). known_tails lists record tails this patch accepts
    and rebuilds on a re-run: its older versions and later patches' records appended after its own.
    """
    append = list(append)
    data = bytearray(source)
    section_count = struct.unpack_from(">I", data, 0)[0]

    def section_start(index):
        return 4 + struct.unpack_from(">I", data, 4 + 4 * index)[0]

    base = section_start(bank)
    end = section_start(bank + 1) if bank + 1 < section_count else len(data)
    count = struct.unpack_from(">I", data, base)[0]
    offsets = [struct.unpack_from(">I", data, base + 4 + 4 * i)[0] for i in range(count)]
    bounds = [base + 4 + offset for offset in offsets] + [end]
    records = [bytes(data[bounds[i]:bounds[i + 1]]) for i in range(count)]
    if count != bank_records:
        # accept the extra records of this patch or of an earlier version of it, then rebuild them
        for tail in (append, *known_tails):
            if count == bank_records + len(tail) and records[bank_records:] == list(tail):
                records = records[:bank_records]
                break
        else:
            raise RuntimeError(f"{label}: bank {bank} has {count} records with unknown extras")
    for index, new in replacements.items():
        records[index] = new
    records.extend(append)

    position = 4 + 4 * len(records)
    new_offsets = []
    for rec in records:
        new_offsets.append(position - 4)
        position += len(rec)
    block = struct.pack(">I", len(records)) + struct.pack(f">{len(records)}I", *new_offsets) + b"".join(records)
    delta = len(block) - (end - base)
    data[base:end] = block
    for index in range(bank + 1, section_count):
        pos = 4 + 4 * index
        struct.pack_into(">I", data, pos, struct.unpack_from(">I", data, pos)[0] + delta)
    return data


def build_bank(records):
    """One bank: u32 record count, the record offsets (relative to the bank start + 4), the records."""
    position = 4 + 4 * len(records)
    offsets = []
    for rec in records:
        offsets.append(position - 4)
        position += len(rec)
    return struct.pack(">I", len(records)) + struct.pack(f">{len(records)}I", *offsets) + b"".join(records)


def bank_records(data, bank):
    """The records of `bank`, as bytes (each with its padding)."""
    _, start, end = _bounds(data, bank)
    count = struct.unpack_from(">I", data, start)[0]
    offsets = struct.unpack_from(f">{count}I", data, start + 4)
    bounds = [start + 4 + offset for offset in offsets] + [end]
    return [bytes(data[bounds[i]:bounds[i + 1]]) for i in range(count)]


def set_bank(source, bank, records, label, known=()):
    """Return source with `bank` = `records`, a bank added after the existing ones.

    The file must have exactly `bank` banks (the bank is appended) or `bank` + 1 whose last bank is
    `records` or one of the record lists in `known` (an older version of this patch's bank, rebuilt)."""
    records = list(records)
    count = struct.unpack_from(">I", source, 0)[0]
    if count == bank + 1:
        if bank_records(source, bank) not in (records, *map(list, known)):
            raise RuntimeError(f"{label}: bank {bank:#x} already holds different records")
    elif count != bank:
        raise RuntimeError(f"{label}: {count} message banks, expected {bank} or {bank + 1}")
    banks = [bytes(source[start:end]) for start, end in (_bounds(source, i)[1:] for i in range(bank))]
    banks.append(build_bank(records))
    offsets, position = [], 4 * len(banks)
    for blob in banks:
        offsets.append(position)
        position += len(blob)
    return bytearray(struct.pack(f">I{len(banks)}I", len(banks), *offsets) + b"".join(banks))
