"""Tiny synthetic game files for the unit tests. Nothing here reads the user's disc.

Each builder writes the smallest file that the matching tools.lib reader accepts. The layouts
are described next to each function; they mirror what the readers in tools/lib walk.
"""
import struct

from tools.lib import mpdata
from tools.lib.rel import R_DOLPHIN_END, R_DOLPHIN_SECTION


# --- DOL -------------------------------------------------------------------------------------
# 0x100-byte header: u32 file offset[7 text + 11 data] at 0x00, u32 load address[18] at 0x48,
# u32 size[18] at 0x90. Text slots are 0-6, data slots 7-17. Section payloads follow the header.

def make_dol(sections):
    """sections: [(kind, address, payload)], kind "text" or "data", slots filled in order."""
    header = bytearray(0x100)
    body = bytearray()
    next_slot = {"text": 0, "data": 7}
    for kind, address, payload in sections:
        slot = next_slot[kind]
        next_slot[kind] += 1
        struct.pack_into(">I", header, 0x00 + 4 * slot, 0x100 + len(body))
        struct.pack_into(">I", header, 0x48 + 4 * slot, address)
        struct.pack_into(">I", header, 0x90 + 4 * slot, len(payload))
        body += payload
    return header + body


# --- messdata*.bin ---------------------------------------------------------------------------
# File: u32 bank_count, u32 offset[bank] (relative to byte 4), then the banks.
# Bank: u32 record_count, u32 offset[record] (relative to bank start + 4), then the records.

def make_bank(records):
    out = bytearray(struct.pack(">I", len(records)))
    position = 4 * len(records)
    for rec in records:
        out += struct.pack(">I", position)
        position += len(rec)
    for rec in records:
        out += rec
    return out


def make_messdata(banks):
    blobs = [make_bank(records) for records in banks]
    out = bytearray(struct.pack(">I", len(blobs)))
    position = 4 * len(blobs)
    for blob in blobs:
        out += struct.pack(">I", position)
        position += len(blob)
    for blob in blobs:
        out += blob
    return out


def bank_bounds(data, bank):
    count = struct.unpack_from(">I", data, 0)[0]
    start = 4 + struct.unpack_from(">I", data, 4 + 4 * bank)[0]
    end = 4 + struct.unpack_from(">I", data, 8 + 4 * bank)[0] if bank + 1 < count else len(data)
    return start, end


def read_bank(data, bank):
    """The records of one bank, as a list of bytes."""
    start, end = bank_bounds(data, bank)
    count = struct.unpack_from(">I", data, start)[0]
    bounds = [start + 4 + struct.unpack_from(">I", data, start + 4 + 4 * i)[0] for i in range(count)] + [end]
    return [bytes(data[bounds[i]:bounds[i + 1]]) for i in range(count)]


def read_banks(data):
    return [read_bank(data, b) for b in range(struct.unpack_from(">I", data, 0)[0])]


# --- REL -------------------------------------------------------------------------------------
# Only the header fields tools.lib.rel uses are filled in:
#   0x0C u32 section count, 0x10 u32 section table offset,
#   0x24 u32 relOffset, 0x28 u32 impOffset, 0x2C u32 impSize.
# Section table: 8 bytes per section (u32 file offset | exec bit 0, u32 size); section 1 = .text.
# Import table: 8 bytes per module (u32 module id, u32 relocation list offset).
# Relocation record: u16 delta from previous, u8 type, u8 target section, u32 addend.

REL_HEADER_SIZE = 0x4C
SELF_MODULE = 7


def reloc_list(relocs):
    """relocs: [(text_offset, kind, target_section, addend)] in ascending offset order."""
    out = bytearray(struct.pack(">HBBI", 0, R_DOLPHIN_SECTION, 1, 0))
    previous = 0
    for offset, kind, target_section, addend in relocs:
        out += struct.pack(">HBBI", offset - previous, kind, target_section, addend)
        previous = offset
    return out + struct.pack(">HBBI", 0, R_DOLPHIN_END, 0, 0)


def make_rel(text, relocs=(), self_relocs=(), module0_last=True):
    """A REL with one .text section and import blocks for itself and for module 0 (the DOL).

    By default the module-0 block is the last thing in the file, which add_calls needs.
    """
    section_table = REL_HEADER_SIZE
    text_offset = section_table + 2 * 8
    text_offset += -text_offset % 0x20
    imp_offset = text_offset + len(text)
    imp_offset += -imp_offset % 4
    lists = {0: reloc_list(relocs), SELF_MODULE: reloc_list(self_relocs)}
    order = [SELF_MODULE, 0] if module0_last else [0, SELF_MODULE]

    out = bytearray(imp_offset + 8 * len(order))
    struct.pack_into(">I", out, 0x00, SELF_MODULE)
    struct.pack_into(">I", out, 0x0C, 2)
    struct.pack_into(">I", out, 0x10, section_table)
    struct.pack_into(">II", out, section_table + 8, text_offset | 1, len(text))
    out[text_offset:text_offset + len(text)] = text
    position = len(out)
    struct.pack_into(">I", out, 0x24, position)
    struct.pack_into(">II", out, 0x28, imp_offset, 8 * len(order))
    for i, module in enumerate(order):
        struct.pack_into(">II", out, imp_offset + 8 * i, module, position)
        position += len(lists[module])
    for module in order:
        out += lists[module]
    return out


# --- data/*.bin archives ---------------------------------------------------------------------
# u32 count, u32 offset[count] (absolute), then each file as mpdata.pack_file writes it.

def make_archive(payloads, packed=None):
    """payloads are packed with pack_file; `packed` replaces some of them with raw blobs."""
    packed = dict(packed or {})
    blobs = [packed.get(i, None) or mpdata.pack_file(p) for i, p in enumerate(payloads)]
    out = bytearray(struct.pack(">I", len(blobs)))
    position = 4 + 4 * len(blobs)
    offsets = []
    for blob in blobs:
        offsets.append(position)
        out += struct.pack(">I", position)
        position += len(blob)
    for blob in blobs:
        out += blob
    return bytes(out), offsets


# --- board file 0: the space (masu) table ----------------------------------------------------
# u32 count, then per space a 46-byte record followed by u16 links[link_count].
# In the record: u32 flags at +38, u16 kind at +42, u16 link count at +44.

SPACE_SIZE = 46


def make_board_file0(spaces):
    """spaces: [(flags, kind, links)]."""
    out = bytearray(struct.pack(">I", len(spaces)))
    for flags, kind, links in spaces:
        rec = bytearray(SPACE_SIZE)
        struct.pack_into(">I", rec, 38, flags)
        struct.pack_into(">HH", rec, 42, kind, len(links))
        out += rec + struct.pack(f">{len(links)}H", *links)
    return out


# --- GameCube disc image (GCM) ---------------------------------------------------------------
# boot.bin (0x440 bytes) at 0: game id, then u32 DOL offset at 0x420, FST offset 0x424, FST size
# 0x428 and max FST size 0x42C. bi2.bin (0x2000) at 0x440. The apploader at 0x2440: a 0x20-byte
# header with u32 body size at +0x14 and trailer size at +0x18. The FST is 12-byte entries (root
# directory first), then the name table. A directory entry is u32 0x01000000|name offset, parent
# index, index after its last descendant; a file entry is u32 name offset, data offset, size.

def make_gcm(files, game_id=b"GP6P01", dol=None):
    """files: {"dir/name.bin": bytes}, paths relative to the disc's files/ root."""
    dol = dol or make_dol([("text", 0x80003100, b"\x60\x00\x00\x00" * 8)])
    tree = {}
    for path, data in files.items():
        node = tree
        *dirs, name = path.split("/")
        for d in dirs:
            node = node.setdefault(d, {})
        node[name] = data

    entries, names = [], bytearray()

    def add(node, parent):
        for name in sorted(node, key=str.lower):
            name_offset = len(names)
            names.extend(name.encode() + b"\0")
            child = node[name]
            if isinstance(child, dict):
                index = len(entries)
                entries.append(["dir", name_offset, parent, None])
                add(child, index)
                entries[index][3] = len(entries)
            else:
                entries.append(["file", name_offset, child])

    entries.append(["dir", 0, 0, None])
    add(tree, 0)
    entries[0][3] = len(entries)

    dol_offset = 0x2500
    fst_offset = dol_offset + len(dol) + (-len(dol) % 0x100)
    fst_size = 12 * len(entries) + len(names)
    data_offset = fst_offset + fst_size + (-(fst_offset + fst_size) % 4)

    fst, body = bytearray(), bytearray()
    for entry in entries:
        if entry[0] == "dir":
            fst += struct.pack(">III", 0x01000000 | entry[1], entry[2], entry[3])
        else:
            fst += struct.pack(">III", entry[1], data_offset + len(body), len(entry[2]))
            body += entry[2] + bytes(-len(entry[2]) % 4)
    fst += names

    disc = bytearray(data_offset)
    disc[0:6] = game_id
    struct.pack_into(">IIII", disc, 0x420, dol_offset, fst_offset, fst_size, fst_size)
    struct.pack_into(">II", disc, 0x2440 + 0x14, 0x20, 0)       # apploader: 0x20 body, no trailer
    disc[dol_offset:dol_offset + len(dol)] = dol
    disc[fst_offset:fst_offset + len(fst)] = fst
    return bytes(disc + body)
