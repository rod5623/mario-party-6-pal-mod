"""tools.lib.mpdata: data/*.bin archives and the CMPR texture codec."""
import struct

import pytest
from PIL import Image

from tests.builders import make_archive
from tools.lib import mpdata

PAYLOADS = [b"first file", bytes(range(256)) * 3, b"x"]


def test_pack_file_layout():
    blob = mpdata.pack_file(b"hello")
    size, kind, size2, compressed = struct.unpack_from(">IIII", blob, 0)
    assert (size, kind, size2) == (5, mpdata.TYPE_ZLIB, 5)
    assert len(blob) % 4 == 0 and len(blob) >= 16 + compressed


def test_read_file_round_trip():
    data, offsets = make_archive(PAYLOADS)
    assert [mpdata.read_file(data, offsets, i) for i in range(3)] == PAYLOADS


def test_read_file_uncompressed_and_unknown_type():
    raw = struct.pack(">II", 3, mpdata.TYPE_NONE) + b"abc\0"
    bad = struct.pack(">II", 3, 5) + b"abc\0"
    data, offsets = make_archive([b"", b"", b"z"], packed={0: raw, 1: bad})
    assert mpdata.read_file(data, offsets, 0) == b"abc"
    with pytest.raises(ValueError):
        mpdata.read_file(data, offsets, 1)


def test_read_archive(tmp_path):
    data, offsets = make_archive(PAYLOADS)
    path = tmp_path / "a.bin"
    path.write_bytes(data)
    assert mpdata.read_archive(path) == (data, offsets)


def test_file_bounds():
    data, offsets = make_archive(PAYLOADS)
    assert mpdata.file_bounds(data, offsets, 0) == (offsets[0], offsets[1])
    assert mpdata.file_bounds(data, offsets, 2) == (offsets[2], len(data))


def test_append_files():
    data, offsets = make_archive(PAYLOADS)
    new = [b"appended", b"another one"]
    out, out_offsets = mpdata.append_files(data, offsets, new)
    assert struct.unpack_from(">I", out, 0)[0] == 5
    assert list(struct.unpack_from(">5I", out, 4)) == out_offsets
    assert [mpdata.read_file(out, out_offsets, i) for i in range(5)] == PAYLOADS + new
    # the old files' bytes are unchanged, just moved down by the bigger offset table
    for i in range(3):
        old = data[slice(*mpdata.file_bounds(data, offsets, i))]
        assert out[out_offsets[i]:out_offsets[i] + len(old)] == old


def solid(colour, size=8):
    return Image.new("RGBA", (size, size), colour)


@pytest.mark.parametrize("colour", [(255, 0, 0, 255), (0, 255, 0, 255), (8, 134, 255, 255), (0, 0, 0, 255)])
def test_cmpr_solid_round_trip(colour):
    # colours exactly representable in RGB565 come back unchanged
    data = mpdata.encode_cmpr(solid(colour))
    assert len(data) == 32                       # one 8x8 tile = four 8-byte blocks
    out = mpdata.decode_cmpr(data, 8, 8)
    assert out.tobytes() == bytes(colour) * 64


def test_cmpr_gradient_within_tolerance():
    img = Image.new("RGBA", (16, 16))
    for y in range(16):
        for x in range(16):
            img.putpixel((x, y), (x * 4, 255 - y * 4, 128, 255))
    out = mpdata.decode_cmpr(mpdata.encode_cmpr(img), 16, 16)
    # CMPR is lossy: four colours per 4x4 block, RGB565 endpoints
    worst = max(abs(a - b) for a, b in zip(img.tobytes(), out.tobytes()))
    assert worst <= 12


def test_cmpr_transparency():
    img = solid((255, 0, 0, 255))
    for x in range(4):
        img.putpixel((x, 0), (0, 0, 0, 0))
    out = mpdata.decode_cmpr(mpdata.encode_cmpr(img), 8, 8)
    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((0, 1)) == (255, 0, 0, 255)


def test_cmpr_keep_copies_blocks():
    keep = mpdata.encode_cmpr(solid((0, 0, 255, 255)))
    data = mpdata.encode_cmpr(solid((255, 0, 0, 255)), keep=(keep, lambda bx, by: bx == 0 and by == 0))
    assert data[:8] == keep[:8] and data[8:] != keep[8:]


def test_parse_anm_bitmaps():
    blob = bytearray(0x40)
    struct.pack_into(">hhhh", blob, 0, 1, 2, 1, 0)
    struct.pack_into(">III", blob, 8, 0x14, 0x18, 0x20)
    struct.pack_into(">BBhhhIII", blob, 0x20, 4, 0x0E, 0, 64, 32, 0x400, 0, 0x100)
    info = mpdata.parse_anm(bytes(blob))
    assert info["banks"] == 1 and info["pats"] == 2
    assert info["bmps"] == [dict(pix=4, fmt=0xE, pal=0, w=64, h=32, size=0x400, pal_o=0, data_o=0x100)]
