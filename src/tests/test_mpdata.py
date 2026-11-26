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


def test_read_file_lz():
    # one flag byte (literal, literal, then a 4-byte reference to the window start, where "AB" landed)
    lz = struct.pack(">II", 6, mpdata.TYPE_LZ) + b"\x03AB" + bytes([958 & 0xFF, (958 >> 2) & ~0x3F | 1])
    data, offsets = make_archive([b"", b"z"], packed={0: lz})
    assert mpdata.read_file(data, offsets, 0) == b"ABABAB"


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


def test_keep_files_undoes_append_files():
    data, offsets = make_archive(PAYLOADS)
    grown, grown_offsets = mpdata.append_files(data, offsets, [b"appended", b"another one"])
    assert mpdata.keep_files(grown, grown_offsets, 3) == (data, offsets)
    assert mpdata.keep_files(data, offsets, 3) == (data, offsets)
    one, one_offsets = mpdata.keep_files(data, offsets, 1)
    assert one_offsets == [8] and mpdata.read_file(one, one_offsets, 0) == PAYLOADS[0]
    with pytest.raises(ValueError):
        mpdata.keep_files(data, offsets, 4)


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


def test_replace_file():
    data, offsets = make_archive(PAYLOADS)
    for index, payload in ((0, b"a much longer first file " * 20), (1, b"short"), (2, b"last one")):
        new, new_offsets = mpdata.replace_file(data, offsets, index, payload)
        expected = list(PAYLOADS)
        expected[index] = payload
        assert [mpdata.read_file(new, new_offsets, i) for i in range(3)] == expected
        assert list(struct.unpack_from(">4I", new, 0)) == [3, *new_offsets]


def test_rgb565_round_trip():
    img = Image.new("RGBA", (8, 4))
    colours = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (248, 252, 248), (0, 0, 0), (16, 32, 64), (200, 100, 8),
               (8, 4, 8)]
    for x, colour in enumerate(colours):
        for y in range(4):
            img.putpixel((x, y), colour + (255,))
    data = mpdata.encode_rgb565(img)
    assert len(data) == 8 * 4 * 2
    back = mpdata.decode_rgb565(data, 8, 4)
    for x, colour in enumerate(colours):
        r, g, b, a = back.getpixel((x, 0))
        assert a == 255 and abs(r - colour[0]) < 8 and abs(g - colour[1]) < 4 and abs(b - colour[2]) < 8


def test_rgb565_tile_order():
    """Pixel (4, 0) is the first of the second 4x4 tile: word 16."""
    img = Image.new("RGB", (8, 4), (0, 0, 0))
    img.putpixel((4, 0), (255, 255, 255))
    data = mpdata.encode_rgb565(img)
    assert struct.unpack_from(">H", data, 32)[0] == 0xFFFF
    assert data.count(b"\xff") == 2


def test_rgb565_rejects_odd_sizes():
    with pytest.raises(ValueError):
        mpdata.encode_rgb565(Image.new("RGB", (6, 4)))


def test_rgb5a3_round_trip():
    # every opaque colour code and every translucent alpha level survive decode -> encode unchanged
    words = [0x8000 | v for v in range(0, 0x8000, 97)] + [a << 12 | v for a in range(8) for v in (0x000, 0x5A3, 0xFFF)]
    words += [0] * (-len(words) % 16)
    raw = struct.pack(f">{len(words)}H", *words)
    w, h = 4 * (len(words) // 16), 4
    image = mpdata.decode_rgb5a3(raw, w, h)
    assert mpdata.encode_rgb5a3(image) == raw


def test_rgb5a3_opaque_only_at_full_alpha():
    image = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    image.putpixel((1, 0), (255, 0, 0, 254))
    words = struct.unpack(">16H", mpdata.encode_rgb5a3(image))
    assert words[0] == 0xFC00 and words[1] == 0x7F00
    with pytest.raises(ValueError):
        mpdata.encode_rgb5a3(Image.new("RGBA", (6, 4)))


def test_c8_round_trip_with_few_colours():
    image = Image.new("RGBA", (16, 8), (255, 0, 0, 255))
    for x in range(8):
        image.putpixel((x, 3), (0, 0, 255, 255))
    image.putpixel((15, 7), (0, 0, 0, 0))
    palette, data, count = mpdata.encode_c8(image)
    assert len(data) == 16 * 8 and len(palette) == 2 * count
    back = mpdata.decode_c8(palette, data, 16, 8)
    assert back.getpixel((0, 0)) == (255, 0, 0, 255) and back.getpixel((2, 3)) == (0, 0, 255, 255)
    assert back.getpixel((15, 7))[3] == 0
    with pytest.raises(ValueError):
        mpdata.encode_c8(Image.new("RGBA", (12, 4)))
