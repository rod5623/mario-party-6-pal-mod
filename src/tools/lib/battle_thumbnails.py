"""Build Battle-roulette thumbnails for the added Battle games.

A thumbnail is a 128x128 CMPR sprite (single bitmap) in data/board*.bin: an octagonal
frame around a picture. The picture of each new thumbnail is the game's instruction
picture (data/instpic.bin, 256x256 CMPR), scaled to fit the frame's opening; the frame
itself comes from an existing thumbnail (file 0x9E).
"""
import math

from PIL import Image, ImageDraw

from tools.lib import mpdata as m

DATA = None  # set by the caller: directory with the original data/*.bin

FRAME_FILE = 0x9E
FIRST_NEW_FILE = 176
BOARD_FILES = ["board", "board_fr", "board_ge", "board_it", "board_sp", "board_us"]

# (instpic file of the day picture, of the night picture) per added game, in table order
INSTPIC = {
    "m604": (10, 8),
    "m615": (31, 30),
    "m614": (29, 28),
    "m603": (4, 3),
}
GAME_ORDER = ["m604", "m615", "m614", "m603"]


def frame_opening(templates):
    """Boolean mask (128x128) of the picture area: inside the inner blue ring."""
    def ringlike(p):
        return abs(p[0] - 0) < 40 and abs(p[1] - 44) < 40 and abs(p[2] - 173) < 45 and p[3] > 200
    radii = {}
    for deg in range(0, 360, 5):
        theta = math.radians(deg)
        found = []
        for im in templates:
            px = im.load()
            r = 30.0
            while r < 66:
                x = int(round(63.5 + r * math.cos(theta)))
                y = int(round(63.5 + r * math.sin(theta)))
                if 0 <= x < 128 and 0 <= y < 128 and ringlike(px[x, y]):
                    found.append(r)
                    break
                r += 0.5
        radii[deg] = min(found) if found else 45.0
    points = [(63.5 + (radii[d] - 1.5) * math.cos(math.radians(d)),
               63.5 + (radii[d] - 1.5) * math.sin(math.radians(d))) for d in range(0, 360, 5)]
    mask = Image.new("L", (128, 128), 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask


def load_anm(data, offsets, index):
    blob = m.read_file(data, offsets, index)
    bmp = m.parse_anm(blob)["bmps"][0]
    return blob, bmp


def anm_image(blob, bmp):
    return m.decode_cmpr(blob[bmp["data_o"]:bmp["data_o"] + bmp["size"]], bmp["w"], bmp["h"])


def build(board_dir, instpic_path, preview_dir=None):
    """Return the list of new thumbnail payloads, ordered (m604 day, m604 night, m615 day, ...)."""
    board, board_offsets = m.read_archive(board_dir / "board.bin")
    templates = []
    for i in range(0x9E, 0xA6):
        blob, bmp = load_anm(board, board_offsets, i)
        templates.append(anm_image(blob, bmp))
    mask = frame_opening(templates)
    frame_blob, frame_bmp = load_anm(board, board_offsets, FRAME_FILE)
    frame_img = templates[0]
    raw = frame_blob[frame_bmp["data_o"]:frame_bmp["data_o"] + frame_bmp["size"]]
    mask_px = mask.load()

    def block_in_opening(bx, by):
        return any(mask_px[bx * 4 + x, by * 4 + y] for y in range(4) for x in range(4))

    pics, pic_offsets = m.read_archive(instpic_path)
    payloads = []
    previews = []
    for game in GAME_ORDER:
        for index in INSTPIC[game]:
            blob = m.read_file(pics, pic_offsets, index)
            bmp = m.parse_anm(blob)["bmps"][0]
            picture = anm_image(blob, bmp).convert("RGBA").resize((96, 96), Image.LANCZOS)
            canvas = frame_img.copy()
            layer = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
            layer.paste(picture, (16, 16))
            canvas.paste(layer, (0, 0), mask)
            data = m.encode_cmpr(canvas, keep=(raw, lambda bx, by: not block_in_opening(bx, by)))
            assert len(data) == frame_bmp["size"]
            payload = bytearray(frame_blob)
            payload[frame_bmp["data_o"]:frame_bmp["data_o"] + frame_bmp["size"]] = data
            payloads.append(bytes(payload))
            previews.append((game, index, m.decode_cmpr(data, 128, 128)))
    if preview_dir:
        sheet = Image.new("RGBA", (136 * 4, 136 * 2), (60, 60, 60, 255))
        for k, (_, _, im) in enumerate(previews):
            sheet.alpha_composite(im, ((k % 4) * 136, (k // 4) * 136))
        sheet.save(preview_dir / "new_thumbnails.png")
    return payloads
