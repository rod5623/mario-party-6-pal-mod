"""Pagoda Peak's board-name label on the party results screen (mdpresult.bin files 89-93).

MP6's labels are one sprite animation per language (mdpresult.bin 89 English, 90 German, 91 French,
92 Italian, 93 Spanish): one 136x240 RGB565 bitmap holding six 136x40 labels, one pattern and one bank per
board (0-5); mdpresultdll picks the bank with HuSprBankSet(group, 1, board). Each label is the board's
name on a pill-shaped frame.

Pagoda Peak's label (bank 6) is built from MP6's Snowflake Lake pill (bank 3) with its lettering cleared,
and MP7's own "Pagoda Peak" lettering: MP7 bdresult*.bin (one per language) holds the six MP7 board
names as a 6-bank 192x192 RGB565 sprite (file 101 in bdresult.bin, 100 in the other languages); bank 1 is
Pagoda Peak. Its background colour is keyed out, and a name with a space is split there over two lines
(as MP6 sets "Snowflake / Lake"); a single word (German "Pagodia") gets one larger line.
"""
import struct

from PIL import Image

from tools.lib import mp7, mpdata

LABEL_FILES = {89: "bdresult", 90: "bdresult_ge", 91: "bdresult_fr", 92: "bdresult_it", 93: "bdresult_sp"}
MP7_NAME_FILE = {"bdresult": 101}            # the other languages: 100
MP7_NAME_FILE_DEFAULT = 100
MP7_BANK = 1                                 # Pagoda Peak in MP7's board order
PILL_BANK = 3                                # Snowflake Lake's pill
BOARDS = 6
W, H = 136, 40                               # one label
KEY_DISTANCE = 60                            # colour distance from MP7's background that counts as background
SPLIT_ZONE = (0.3, 0.7)                      # where a word break may fall, as a fraction of the width
MAX_BREAK = 0.35                             # a break column is at most this fraction opaque (the drop shadow)

HEADER = ">hhhhIII"                          # bankNum, patNum, bmpNum, useNum, bank, pat, bmp offsets
PAT = ">hhhhhhI"                             # layerNum, centerX, centerY, sizeX, sizeY, pad, layer offset
LAYER = ">BBhhhhhhh8h"                       # alpha, flip, bmpNo, startX, startY, sizeX, sizeY, shiftX, shiftY, vtx
BANK = ">hhI"                                # timeNum, unk, frame offset
FRAME = ">hhhhhh"                            # pat, time, shiftX, shiftY, flip, pad
BMP = ">BBhhhIII"                            # pixSize, dataFmt, palNum, sizeX, sizeY, dataSize, pal, data


def read_sprite(blob):
    """The parts of a one-bitmap sprite with one layer per pattern and one frame per bank."""
    banks, pats, bmps, use, bank_o, pat_o, bmp_o = struct.unpack_from(HEADER, blob, 0)
    if bmps != 1:
        raise ValueError(f"expected one bitmap, found {bmps}")
    pat_rows = [struct.unpack_from(PAT, blob, pat_o + 16 * i) for i in range(pats)]
    layers = []
    for row in pat_rows:
        if row[0] != 1:
            raise ValueError("expected one layer per pattern")
        layers.append(struct.unpack_from(LAYER, blob, row[6]))
    bank_rows = [struct.unpack_from(BANK, blob, bank_o + 8 * i) for i in range(banks)]
    frames = []
    for row in bank_rows:
        if row[0] != 1:
            raise ValueError("expected one frame per bank")
        frames.append(struct.unpack_from(FRAME, blob, row[2]))
    bmp = struct.unpack_from(BMP, blob, bmp_o)
    if bmp[1] & 0xF != 1:
        raise ValueError(f"expected an RGB565 bitmap, found format {bmp[1] & 0xF}")
    image = mpdata.decode_rgb565(blob[bmp[7]:bmp[7] + bmp[5]], bmp[3], bmp[4])
    return {"use": use, "pats": pat_rows, "layers": layers, "banks": bank_rows, "frames": frames, "bmp": bmp,
            "image": image}


def bank_image(sprite, bank):
    """The bitmap region bank `bank` shows (its frame's pattern's layer)."""
    layer = sprite["layers"][sprite["frames"][bank][0]]
    x, y, w, h = layer[3:7]
    return sprite["image"].crop((x, y, x + w, y + h))


def build_sprite(sprite, labels):
    """A sprite like `sprite` holding `labels` (136x40 images) stacked in one bitmap, one pattern and bank
    each, laid out as MP6 lays out its label sprites."""
    count = len(labels)
    pat_o = struct.calcsize(HEADER)
    layer_o = pat_o + 16 * count
    bank_o = layer_o + 32 * count
    frame_o = bank_o + 8 * count
    bmp_o = frame_o + 12 * count
    data_o = (bmp_o + struct.calcsize(BMP) + 31) & ~31
    image = Image.new("RGB", (W, H * count))
    for i, label in enumerate(labels):
        image.paste(label.convert("RGB"), (0, H * i))
    pixels = mpdata.encode_rgb565(image)
    out = bytearray(data_o)
    struct.pack_into(HEADER, out, 0, count, count, 1, sprite["use"], bank_o, pat_o, bmp_o)
    pat0, layer0, bank0, frame0 = sprite["pats"][0], sprite["layers"][0], sprite["banks"][0], sprite["frames"][0]
    for i in range(count):
        struct.pack_into(PAT, out, pat_o + 16 * i, *pat0[:6], layer_o + 32 * i)
        layer = list(layer0)
        layer[4] = H * i                      # startY
        struct.pack_into(LAYER, out, layer_o + 32 * i, *layer)
        struct.pack_into(BANK, out, bank_o + 8 * i, *bank0[:2], frame_o + 12 * i)
        struct.pack_into(FRAME, out, frame_o + 12 * i, i, *frame0[1:])
    bmp = list(sprite["bmp"])
    bmp[4], bmp[5], bmp[6], bmp[7] = H * count, len(pixels), data_o, data_o
    struct.pack_into(BMP, out, bmp_o, *bmp)
    return bytes(out) + pixels


def check_layout(sprite):
    """Raise unless `sprite` is laid out as build_sprite writes it: bank i -> pattern i -> rows 40i."""
    for i, (frame, layer) in enumerate(zip(sprite["frames"], sprite["layers"])):
        if frame[0] != i or tuple(layer[3:7]) != (0, H * i, W, H):
            raise ValueError(f"label sprite bank {i} is not laid out as expected")


def blank_pill(label):
    """`label` with everything inside its white ring painted the pill's colour (the lettering cleared)."""
    pill = label.convert("RGB").copy()
    px = pill.load()
    white = (255, 255, 255)
    fill = max(pill.getcolors(W * H), key=lambda c: c[0])[1]     # the pill's colour covers the most pixels
    for y in range(H):
        if px[W // 2, y] == white:        # the ring's top and bottom rows
            continue
        row = [px[x, y] for x in range(W)]
        if white not in row[:W // 2] or white not in row[W // 2:]:
            continue
        left = max(x for x in range(W // 2) if row[x] == white) + 2
        right = min(x for x in range(W // 2, W) if row[x] == white) - 2
        for x in range(left, right + 1):
            px[x, y] = fill
    return pill


def mp7_name(language_file):
    """MP7's "Pagoda Peak" lettering for one language, background keyed out, cropped to the letters."""
    data = mp7.read(f"files/data/{language_file}.bin")
    count = struct.unpack_from(">I", data, 0)[0]
    offsets = list(struct.unpack_from(f">{count}I", data, 4))
    number = MP7_NAME_FILE.get(language_file, MP7_NAME_FILE_DEFAULT)
    sprite = read_sprite(mpdata.read_file(data, offsets, number))
    if len(sprite["banks"]) != BOARDS:
        raise ValueError(f"MP7 {language_file}.bin file {number} has {len(sprite['banks'])} banks, expected {BOARDS}")
    name = bank_image(sprite, MP7_BANK).convert("RGBA")
    background = name.getpixel((0, 0))
    px = name.load()
    for y in range(name.height):
        for x in range(name.width):
            if sum(abs(a - b) for a, b in zip(px[x, y][:3], background[:3])) < KEY_DISTANCE:
                px[x, y] = (0, 0, 0, 0)
    return name.crop(name.getbbox())


def split_words(name):
    """The lettering split at the emptiest column near the middle (a space; the drop shadow may fill it
    partly), or [name] when no column there is empty enough (one word)."""
    alpha = name.getchannel("A").load()
    lo, hi = (int(name.width * f) for f in SPLIT_ZONE)
    counts = {x: sum(alpha[x, y] > 0 for y in range(name.height)) for x in range(lo, hi)}
    column = min(counts, key=lambda x: (counts[x], abs(x - name.width / 2)))
    if counts[column] > MAX_BREAK * name.height:
        return [name]
    words = [name.crop((0, 0, column, name.height)), name.crop((column + 1, 0, name.width, name.height))]
    return [word.crop(word.getbbox()) for word in words]


def _paste(canvas, image, box):
    x0, y0, x1, y1 = box
    image = image.copy()
    image.thumbnail((x1 - x0, y1 - y0), Image.LANCZOS)
    canvas.alpha_composite(image, (x0 + (x1 - x0 - image.width) // 2, y0 + (y1 - y0 - image.height) // 2))


def compose(pill, name):
    """The label: `name` on `pill`, on two lines when it splits into two words."""
    canvas = pill.convert("RGBA")
    words = split_words(name)
    if len(words) == 2:
        _paste(canvas, words[0], (12, 3, W - 12, 21))
        _paste(canvas, words[1], (12, 19, W - 12, 37))
    else:
        _paste(canvas, name, (10, 6, W - 10, 34))
    return canvas.convert("RGB")


def label_sprite(vanilla_blob, language_file):
    """The vanilla 6-label sprite `vanilla_blob` with Pagoda Peak's label added as bank 6."""
    sprite = read_sprite(vanilla_blob)
    if len(sprite["banks"]) != BOARDS:
        raise ValueError(f"label sprite has {len(sprite['banks'])} banks, expected {BOARDS}")
    check_layout(sprite)
    labels = [bank_image(sprite, i) for i in range(BOARDS)]
    labels.append(compose(blank_pill(labels[PILL_BANK]), mp7_name(language_file)))
    return build_sprite(sprite, labels)
