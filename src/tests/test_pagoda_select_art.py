"""tools/pagoda/select_art.py: sprite files with an extra bank and replaced pixels (synthetic sprites)."""
import struct

import pytest
from PIL import Image

from tools.lib import mpdata
from tools.pagoda import select_art as art


def sprite(w, h, colour):
    """A one-bank, one-pattern, one-layer RGB5A3 sprite laid out like the vanilla banner files."""
    out = bytearray(128)
    struct.pack_into(art.HEADER, out, 0, 1, 1, 1, 0, 68, 20, 88)
    struct.pack_into(art.PAT, out, 20, 1, w // 2, h // 2, w, h, 0, 36)
    struct.pack_into(art.LAYER, out, 36, 255, 0, 0, 0, 0, w, h, 0, 0, 0, 0, w, 0, w, h, 0, h)
    struct.pack_into(art.BANK, out, 68, 1, 0, 76)
    struct.pack_into(art.FRAME, out, 76, 0, 1, 0, 0, 0, 0)
    pixels = mpdata.encode_rgb5a3(Image.new("RGBA", (w, h), colour))
    struct.pack_into(art.BMP, out, 88, 16, art.RGB5A3, 0, w, h, len(pixels), 128, 128)
    return bytes(out) + pixels


def test_add_bank_keeps_bank_zero_and_appends_bank_one():
    blob = sprite(8, 4, (255, 0, 0, 255))
    out = art.add_bank(blob, Image.new("RGBA", (8, 4), (0, 0, 255, 255)))
    assert art.bank_count(out) == 2
    w, h, data_o, size = art.bitmap(out)
    assert (w, h) == (8, 8)
    old = art.bitmap(blob)
    assert out[data_o:data_o + old[3]] == blob[old[2]:old[2] + old[3]]
    image = art.image(out)
    assert image.getpixel((0, 0))[:3] == (255, 0, 0) and image.getpixel((0, 7))[:3] == (0, 0, 255)
    _, _, _, _, bank_o, pat_o, _ = struct.unpack_from(art.HEADER, out, 0)
    layer1 = struct.unpack_from(art.LAYER, out, struct.unpack_from(art.PAT, out, pat_o + 16)[6])
    frame1 = struct.unpack_from(art.FRAME, out, struct.unpack_from(art.BANK, out, bank_o + 8)[2])
    assert layer1[4] == 4 and frame1[0] == 1
    assert data_o % 32 == 0


def test_add_bank_refuses_wrong_size_and_two_banks():
    blob = sprite(8, 4, (0, 0, 0, 255))
    with pytest.raises(ValueError):
        art.add_bank(blob, Image.new("RGBA", (4, 4)))
    two = art.add_bank(blob, Image.new("RGBA", (8, 4)))
    with pytest.raises(ValueError):
        art.add_bank(two, Image.new("RGBA", (8, 4)))


def test_replace_image_keeps_the_header():
    blob = sprite(8, 4, (0, 0, 0, 255))
    out = art.replace_image(blob, Image.new("RGBA", (8, 4), (0, 255, 0, 255)))
    assert out[:128] == blob[:128] and len(out) == len(blob)
    assert art.image(out).getpixel((3, 2))[:3] == (0, 255, 0)


def test_night_is_darker_and_bluer():
    day = Image.new("RGB", (4, 4), (200, 180, 120))
    r, g, b = art.night(day).getpixel((0, 0))
    assert r < 200 and g < 180 and b > r and b > g


def test_square_pads_a_narrow_render():
    render = Image.new("RGB", (40, 100), (10, 200, 10))
    out = art.square(render, 0, 100)
    assert out.size == (100, 100) and out.getpixel((50, 50)) == (10, 200, 10)


def test_c8_sprite_banks_and_alignment():
    template = sprite(8, 4, (0, 0, 0, 255))
    img = Image.new("RGBA", (16, 8), (0, 255, 0, 255))
    out = art.c8_sprite(template, img, [(0, 0, 8, 8), (8, 0, 8, 8)])
    banks, pats, bmps, use, bank_o, pat_o, bmp_o = struct.unpack_from(art.HEADER, out, 0)
    assert (banks, pats, bmps) == (2, 2, 1)
    pix, fmt, pal_n, w, h, size, pal_o, data_o = struct.unpack_from(art.BMP, out, bmp_o)
    assert (pix, fmt, w, h, size) == (8, art.C8, 16, 8, 128) and pal_o % 32 == 0 and data_o % 32 == 0
    layer1 = struct.unpack_from(art.LAYER, out, struct.unpack_from(art.PAT, out, pat_o + 16)[6])
    assert layer1[3:7] == (8, 0, 8, 8)
    assert art.any_image(out).getpixel((12, 4))[:3] == (0, 255, 0)
