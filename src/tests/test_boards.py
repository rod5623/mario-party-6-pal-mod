"""tools.lib.boards: space table offsets, the LZ decoder and file 0 replacement."""
import struct

import pytest

from tests.builders import SPACE_SIZE, make_archive, make_board_file0
from tools.lib import boards, mpdata

SPACES = [(0x11, 1, []), (0x22, 2, [3, 4, 5]), (0x33, 3, [1])]


def test_flag_and_kind_offsets():
    blob = make_board_file0(SPACES)
    space3 = 4 + SPACE_SIZE + (SPACE_SIZE + 2 * 3)       # space 2 has three links
    assert boards.flag_offset(blob, 1) == 4 + 38
    assert boards.kind_offset(blob, 1) == 4 + 42
    assert boards.flag_offset(blob, 3) == space3 + 38
    assert boards.kind_offset(blob, 3) == space3 + 42
    for number, (flags, kind, _) in enumerate(SPACES, 1):
        assert struct.unpack_from(">I", blob, boards.flag_offset(blob, number))[0] == flags
        assert struct.unpack_from(">H", blob, boards.kind_offset(blob, number))[0] == kind


@pytest.mark.parametrize("space_id", [0, 4])
def test_offsets_missing_space(space_id):
    blob = make_board_file0(SPACES)
    with pytest.raises(ValueError):
        boards.flag_offset(blob, space_id)
    with pytest.raises(ValueError):
        boards.kind_offset(blob, space_id)


# HuDecodeLz (decode type 1): a flag byte, read LSB first, says per item whether it is a literal
# (1) or a back-reference (0). A back-reference is 2 bytes: a 10-bit position in a 1024-byte ring
# buffer (low 8 bits, then the top 2 bits of the second byte) and a length (low 6 bits + 3).
# The ring buffer starts zero-filled with the write position at 958 (0x3BE).

def ref(position, length):
    return bytes([position & 0xFF, ((position >> 8) << 6) | (length - 3)])


def test_lz_literals():
    assert boards.lz_decode(b"\xff" + b"ABCDEFGH" + b"\x01" + b"I", 9) == b"ABCDEFGHI"


def test_lz_back_reference():
    stream = bytes([0b0111]) + b"ABC" + ref(958, 3)
    assert boards.lz_decode(stream, 6) == b"ABCABC"


def test_lz_overlapping_reference():
    stream = bytes([0b011]) + b"AB" + ref(958, 5)
    assert boards.lz_decode(stream, 7) == b"ABABABA"


def test_lz_reference_into_zeroed_buffer_and_size_cut():
    stream = bytes([0b10]) + ref(0, 4) + b"Z"
    assert boards.lz_decode(stream, 5) == b"\0\0\0\0Z"
    assert boards.lz_decode(stream, 3) == b"\0\0\0"


def test_load_and_replace_file0():
    file0 = make_board_file0(SPACES)
    data, offsets = make_archive([bytes(file0), b"model", b"texture"])
    blob, start, end = boards.load_spaces(data, offsets)
    assert blob == file0 and (start, end) == (offsets[0], offsets[1])

    struct.pack_into(">H", blob, boards.kind_offset(blob, 2), 9)
    blob += b"\0" * 300                                     # change the packed size
    out, new_offsets = boards.replace_file0(data, offsets, start, end, blob)
    assert list(struct.unpack_from(">3I", out, 4)) == new_offsets
    assert new_offsets[0] == offsets[0]
    delta = new_offsets[1] - offsets[1]
    assert delta == len(mpdata.pack_file(bytes(blob))) - (end - start)
    assert new_offsets[2] == offsets[2] + delta
    assert mpdata.read_file(out, new_offsets, 0) == bytes(blob)
    assert [mpdata.read_file(out, new_offsets, i) for i in (1, 2)] == [b"model", b"texture"]


def test_load_spaces_lz_file0():
    file0 = make_board_file0(SPACES[:1])
    literal = b"".join(b"\xff" + file0[i:i + 8] for i in range(0, len(file0), 8))
    raw = struct.pack(">II", len(file0), 1) + literal
    raw += b"\0" * (-len(raw) % 4)
    data, offsets = make_archive([b"", b"rest"], packed={0: raw})
    blob, _, _ = boards.load_spaces(data, offsets)
    assert blob == file0
