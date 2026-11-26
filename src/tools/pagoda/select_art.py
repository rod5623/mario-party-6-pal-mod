"""Pagoda Peak on the party board select (page 2 of apply_party_pages_patch.py): its pictures and banner.

MP7 has no MP6-style board select art, so the pictures are made from a render of the whole board that the
user supplies (RENDER, git-ignored under src/orig/; e.g. the Super Mario Wiki's "Pagoda Peak - Mario Party 7"
board image, 1575x2000):
  * icon: MP6's octagon picture, 512x256 with two banks (day left, night right), laid out as
    mdparty.bin 0x63-0x68 but C8 (c8_sprite) to save memory. The frame is MP6's (the same pink in all six); the picture area is where the six
    vanilla icons differ, and the render (padded at the sides with its own blurred edges) is fitted into it.
    The night half is the day picture tinted dark blue (night()).
  * half-disc: 256x256 C8 day and night pictures in the shape of mdparty.bin 0x06 (its alpha), from a
    closer square of the render.
  * empty icon (page slots with no board yet): the octagon frame around a plain slate interior with a "?",
    at a quarter of the size (EMPTY_SIZE; 3D texture regions are relative to the bitmap's size).
Memory: the board select reads all its pictures into one heap when the party menu opens, before the character
models; the first build (all RGB5A3, about 790 KB more) made character models fail to load (invalid reads in
memcpy from Hu3DModelLink). So the new pictures are C8, and the twelve vanilla half-disc pictures and the
sun / moon (0x04-0x11, 2D sprites) are re-encoded as C8 too (vanilla_discs_c8), which frees more than the new
files use.
  * banner: MP7's own "Pagoda Peak" lettering (label.mp7_name, one per language) with a soft white glow, as a
    second bank of the slot's banner files (mdparty.bin 0x32 + language, 248x48 RGB5A3), since the banner
    sprites are created once and only their bank can change.
Sprite files keep the vanilla header layout; add_bank() stacks a bank below the vanilla bitmap and leaves the
vanilla bytes as they were.
"""
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from tools.lib import mpdata
from tools.lib.paths import ORIG

RENDER = ORIG.parent / "pagoda_screens" / "Pagoda_Peak_-_Mario_Party_7.png"   # src/orig/pagoda_screens/
ICON_FILES = range(0x63, 0x69)       # the six vanilla board icons (one frame, six pictures)
DISC_FILE = 0x06                     # Towering Treetop's half-disc by day: the shape
VANILLA_DISCS = range(0x04, 0x12)    # sun, moon and the six boards' half-discs by day / night (256x256 RGB5A3)
BANNER_FIRST = 0x32                  # slot 0's banner files, + language (English, German, French, Italian, Spanish)
LANGUAGES = 5
HALF = 256                           # one octagon in the icon bitmap
ICON_CROP = (0, 2000)                # the render's square for the icon: top row and size
DISC_CROP = (150, 1700)              # ... and for the half-disc
FRAME_VARIANCE = 6                   # a pixel the six icons share (std below this) is frame
PICTURE_VARIANCE = 12                # a pixel where they differ (std above this) is picture
EMPTY_TOP, EMPTY_BOTTOM = (92, 104, 124), (52, 60, 78)

HEADER = ">hhhhIII"                  # bankNum, patNum, bmpNum, useNum, bank, pat, bmp offsets
PAT = ">hhhhhhI"                     # layerNum, centerX, centerY, sizeX, sizeY, pad, layer offset
LAYER = ">BBhhhhhhh8h"               # alpha, flip, bmpNo, startX, startY, sizeX, sizeY, shiftX, shiftY, vtx
BANK = ">hhI"                        # timeNum, unk, frame offset
FRAME = ">hhhhhh"                    # pat, time, shiftX, shiftY, flip, pad
BMP = ">BBhhhIII"                    # pixSize, dataFmt, palNum, sizeX, sizeY, dataSize, pal, data
RGB5A3, C8 = 2, 3
EMPTY_SIZE = (128, 64)             # the empty-slot icon is small: a flat picture, and memory is tight


# --- sprite files -------------------------------------------------------------------------------------
def bitmap(blob):
    """(width, height, data offset, data size) of a one-bitmap RGB5A3 sprite."""
    banks, pats, bmps, use, bank_o, pat_o, bmp_o = struct.unpack_from(HEADER, blob, 0)
    _, fmt, _, w, h, size, _, data_o = struct.unpack_from(BMP, blob, bmp_o)
    if bmps != 1 or fmt & 0xF != RGB5A3:
        raise ValueError(f"expected one RGB5A3 bitmap, found {bmps} (format {fmt & 0xF})")
    return w, h, data_o, size


def image(blob):
    w, h, data_o, size = bitmap(blob)
    return mpdata.decode_rgb5a3(blob[data_o:data_o + size], w, h)


def replace_image(blob, img):
    """`blob` with its bitmap's pixels replaced by `img` (same size); the header is kept."""
    w, h, data_o, size = bitmap(blob)
    if img.size != (w, h):
        raise ValueError(f"image is {img.size}, the sprite's bitmap {w}x{h}")
    return blob[:data_o] + mpdata.encode_rgb5a3(img) + blob[data_o + size:]


def c8_sprite(template, img, rects):
    """A C8 sprite of `img` with one bank per rectangle (x, y, w, h) of it, each one pattern with one layer.
    The fields that aren't geometry (use count, layer alpha and flip, frame time) come from `template`, a
    vanilla sprite's first pattern, layer, bank and frame. Palette and pixels sit at 32-byte boundaries (GX
    loads both by DMA). Half the memory of RGB5A3: the board select loads every picture when the party menu
    opens, into the heap the menu's character models need too."""
    _, _, _, use, bank_o, pat_o, _ = struct.unpack_from(HEADER, template, 0)
    pat = struct.unpack_from(PAT, template, pat_o)
    layer = struct.unpack_from(LAYER, template, pat[6])
    bank = struct.unpack_from(BANK, template, bank_o)
    frame = struct.unpack_from(FRAME, template, bank[2])
    palette, pixels, count = mpdata.encode_c8(img)
    n = len(rects)
    new_pat = struct.calcsize(HEADER)
    new_layer = new_pat + n * struct.calcsize(PAT)
    new_bank = new_layer + n * struct.calcsize(LAYER)
    new_frame = new_bank + n * struct.calcsize(BANK)
    new_bmp = new_frame + n * struct.calcsize(FRAME)
    pal_o = (new_bmp + struct.calcsize(BMP) + 31) & ~31
    data_o = (pal_o + len(palette) + 31) & ~31
    out = bytearray(data_o)
    struct.pack_into(HEADER, out, 0, n, n, 1, use, new_bank, new_pat, new_bmp)
    for i, (x, y, w, h) in enumerate(rects):
        struct.pack_into(PAT, out, new_pat + 16 * i, 1, w // 2, h // 2, w, h, pat[5], new_layer + 32 * i)
        struct.pack_into(LAYER, out, new_layer + 32 * i, layer[0], layer[1], 0, x, y, w, h, 0, 0,
                         0, 0, w, 0, w, h, 0, h)
        struct.pack_into(BANK, out, new_bank + 8 * i, 1, bank[1], new_frame + 12 * i)
        struct.pack_into(FRAME, out, new_frame + 12 * i, i, *frame[1:])
    struct.pack_into(BMP, out, new_bmp, 8, C8, count, img.width, img.height, len(pixels), pal_o, data_o)
    out[pal_o:pal_o + len(palette)] = palette
    return bytes(out) + pixels


def any_image(blob):
    """The bitmap of a one-bitmap RGB5A3 or C8 sprite."""
    _, _, _, _, _, _, bmp_o = struct.unpack_from(HEADER, blob, 0)
    _, fmt, pal_n, w, h, size, pal_o, data_o = struct.unpack_from(BMP, blob, bmp_o)
    if fmt & 0xF == C8:
        return mpdata.decode_c8(blob[pal_o:pal_o + 2 * pal_n], blob[data_o:data_o + size], w, h)
    return image(blob)


def add_bank(blob, img):
    """A one-bank, one-pattern, one-layer sprite (`blob`) with `img` (the bitmap's size) as bank 1: the bitmap
    grows down by one image, pattern 1 / bank 1 copy pattern 0 / bank 0 pointing at it. Laid out as the
    vanilla banner files are (header, patterns, layers, banks, frames, bitmap, data at a 32-byte boundary)."""
    banks, pats, bmps, use, bank_o, pat_o, bmp_o = struct.unpack_from(HEADER, blob, 0)
    if (banks, pats, bmps) != (1, 1, 1):
        raise ValueError(f"expected 1 bank, 1 pattern, 1 bitmap; found {banks}, {pats}, {bmps}")
    pat = struct.unpack_from(PAT, blob, pat_o)
    if pat[0] != 1:
        raise ValueError("expected one layer")
    layer = struct.unpack_from(LAYER, blob, pat[6])
    bank = struct.unpack_from(BANK, blob, bank_o)
    if bank[0] != 1:
        raise ValueError("expected one frame")
    frame = struct.unpack_from(FRAME, blob, bank[2])
    bmp = list(struct.unpack_from(BMP, blob, bmp_o))
    w, h, data_o, size = bitmap(blob)
    if img.size != (w, h):
        raise ValueError(f"image is {img.size}, the banner {w}x{h}")
    new_pat, new_layer = struct.calcsize(HEADER), struct.calcsize(HEADER) + 2 * struct.calcsize(PAT)
    new_bank = new_layer + 2 * struct.calcsize(LAYER)
    new_frame = new_bank + 2 * struct.calcsize(BANK)
    new_bmp = new_frame + 2 * struct.calcsize(FRAME)
    new_data = (new_bmp + struct.calcsize(BMP) + 31) & ~31
    out = bytearray(new_data)
    struct.pack_into(HEADER, out, 0, 2, 2, 1, use, new_bank, new_pat, new_bmp)
    for i in range(2):
        struct.pack_into(PAT, out, new_pat + 16 * i, *pat[:6], new_layer + 32 * i)
        moved = list(layer)
        moved[4] = layer[4] + h * i                     # startY
        struct.pack_into(LAYER, out, new_layer + 32 * i, *moved)
        struct.pack_into(BANK, out, new_bank + 8 * i, *bank[:2], new_frame + 12 * i)
        struct.pack_into(FRAME, out, new_frame + 12 * i, i, *frame[1:])
    pixels = blob[data_o:data_o + size] + mpdata.encode_rgb5a3(img)
    bmp[4], bmp[5], bmp[6], bmp[7] = 2 * h, len(pixels), new_data, new_data
    struct.pack_into(BMP, out, new_bmp, *bmp)
    return bytes(out) + pixels


def bank_count(blob):
    return struct.unpack_from(HEADER, blob, 0)[0]


# --- pictures -----------------------------------------------------------------------------------------
def night(img):
    """A day picture as night: darker, cold blue, with the bright parts kept a little."""
    a = np.asarray(img.convert("RGB")).astype(np.float32) / 255
    lum = a @ np.array([0.3, 0.59, 0.11], dtype=np.float32)
    out = (a ** 1.25) * np.array([0.30, 0.38, 0.78]) + (lum[..., None] ** 2.2) * np.array([0.04, 0.06, 0.20])
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


def square(render, top, size):
    """A size x size square of `render` from row `top`; a render narrower than `size` is padded at the sides
    with its own edge columns, stretched and blurred."""
    w, h = render.size
    crop = render.crop((0, top, w, min(h, top + size)))
    if crop.height < size:
        grown = Image.new("RGB", (w, size))
        grown.paste(crop, (0, 0))
        grown.paste(crop.crop((0, crop.height - 2, w, crop.height)).resize((w, size - crop.height)), (0, crop.height))
        crop = grown
    if w >= size:
        left = (w - size) // 2
        return crop.crop((left, 0, left + size, size))
    canvas = Image.new("RGB", (size, size))
    left = (size - w) // 2
    canvas.paste(crop.crop((0, 0, 30, size)).resize((left, size)).filter(ImageFilter.GaussianBlur(25)), (0, 0))
    canvas.paste(crop.crop((w - 30, 0, w, size)).resize((size - w - left, size)).filter(ImageFilter.GaussianBlur(25)),
                 (left + w, 0))
    canvas.paste(crop, (left, 0))
    return canvas


def _hull(points):
    """Convex hull (monotone chain) of (x, y) points."""
    pts = sorted(set(points))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def picture_mask(icons):
    """The octagon's picture area in one 256x256 half: where the vanilla icons' day halves differ, filled out
    to its convex hull, minus the frame pixels they share."""
    days = np.stack([np.asarray(icon.crop((0, 0, HALF, HALF))).astype(np.float32)[..., :3] for icon in icons])
    spread = days.std(axis=0).mean(axis=2)
    ys, xs = np.nonzero(spread > PICTURE_VARIANCE)
    mask = Image.new("L", (HALF, HALF), 0)
    ImageDraw.Draw(mask).polygon(_hull(zip(xs.tolist(), ys.tolist())), fill=255)
    frame = Image.fromarray(((spread < FRAME_VARIANCE) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))
    return Image.fromarray(np.minimum(np.asarray(mask), 255 - np.asarray(frame)))


def octagons(frame_icon, mask, day):
    """`frame_icon` (an icon image) with `day` and night(day) in its two halves' picture areas."""
    box = mask.getbbox()
    day = day.resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
    out = frame_icon.copy()
    for left, picture in ((0, day), (HALF, night(day))):
        layer = Image.new("RGBA", (HALF, HALF))
        layer.paste(picture, box[:2])
        half = out.crop((left, 0, left + HALF, HALF))
        half.paste(layer, (0, 0), mask)
        out.paste(half, (left, 0))
    return out


def icon_picture(render, icons):
    """Pagoda Peak's octagon icon (day and night) from the render and the six vanilla icon images."""
    day = ImageEnhance.Color(square(render, *ICON_CROP)).enhance(1.1)
    return octagons(icons[0], picture_mask(icons), day)


def empty_picture(icons):
    """The icon of an empty page slot: a slate interior with a "?" in the octagon frame."""
    mask = picture_mask(icons)
    x0, y0, x1, y1 = mask.getbbox()
    size = (x1 - x0, y1 - y0)
    inside = Image.new("RGB", size)
    draw = ImageDraw.Draw(inside)
    for y in range(size[1]):
        t = y / max(1, size[1] - 1)
        draw.line([(0, y), (size[0], y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(EMPTY_TOP, EMPTY_BOTTOM)))
    cx, cy, r, width = size[0] // 2, size[1] // 2 - 22, 38, 18
    mark = (236, 236, 244)
    draw.arc((cx - r, cy - r, cx + r, cy + r), 160, 405, fill=mark, width=width)
    draw.rectangle((cx - width // 2, cy + r - 6, cx + width // 2, cy + r + 30), fill=mark)
    draw.ellipse((cx - 13, cy + r + 44, cx + 13, cy + r + 70), fill=mark)
    out = icons[0].copy()
    for left in (0, HALF):
        layer = Image.new("RGBA", (HALF, HALF))
        layer.paste(inside, (x0, y0))
        half = out.crop((left, 0, left + HALF, HALF))
        half.paste(layer, (0, 0), mask)
        out.paste(half, (left, 0))
    return out


def disc_pictures(render, shape):
    """(day, night) half-disc pictures in the shape (alpha) of the vanilla `shape` image."""
    alpha = shape.getchannel("A")
    box = alpha.getbbox()
    picture = square(render, *DISC_CROP).resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
    out = []
    for p in (picture, night(picture)):
        layer = Image.new("RGBA", shape.size)
        layer.paste(p, box[:2])
        layer.putalpha(alpha)
        out.append(layer)
    return out


def banner_picture(lettering, size):
    """MP7's lettering centred on a transparent banner of `size`, with a soft white glow behind it."""
    w, h = size
    name = lettering.copy()
    name.thumbnail((w - 12, h - 6), Image.LANCZOS)
    canvas = Image.new("RGBA", size, (255, 255, 255, 0))
    at = ((w - name.width) // 2, (h - name.height) // 2)
    glow = Image.new("RGBA", size, (255, 255, 255, 0))
    glow.paste((255, 255, 255, 255), at, name.getchannel("A").point(lambda a: 255 if a else 0))
    glow = glow.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(3))
    glow.putalpha(glow.getchannel("A").point(lambda a: a * 3 // 4))
    canvas.alpha_composite(glow)
    canvas.alpha_composite(name, at)
    return canvas


def load_render():
    if not RENDER.exists():
        raise SystemExit(f"{RENDER} is missing: put a render of the whole Pagoda Peak board there "
                         "(see tools/pagoda/select_art.py)")
    return Image.open(RENDER).convert("RGB")
