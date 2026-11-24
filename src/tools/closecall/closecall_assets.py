"""Models and layout shared by the Close Call minigame build and patch scripts.

The models are appended to data/saf.bin (a debug archive only the debug overlays read; retail has 5 files in it),
so the REL loads them as P01_DATA_saf | index. write_header() writes build/GP6P01/include/closecall_files.h with
the indices and sizes the C code uses.

Textures are drawn here (simple original art): a tiled wall with painted down arrows for a sense of speed, a
hazard-striped floor slab, and a grey ledge.
"""

from tools.lib import hsf_build

from tools.lib.paths import ROOT
from tools.lib.paths import ASSETS
HEADER = ROOT / "build" / "GP6P01" / "include" / "closecall_files.h"

SAF_VANILLA_FILES = 5
FILE_WALL, FILE_FLOOR, FILE_LEDGE, FILE_MARKER = 5, 6, 7, 8  # marker: debug head-top bar

WALL_W, WALL_TILE_H, WALL_Z = 1400.0, 500.0, -120.0
FLOOR_W, FLOOR_FRONT_Z, FLOOR_DEPTH = 1400.0, 300.0, 800.0  # deep front face: no void below the floor
LEDGE_W, LEDGE_FRONT_Z, LEDGE_DEPTH = 760.0, 90.0, 40.0

UP, FRONT = (0, 127, 0), (0, 0, 127)


def _normals():
    return bytes(UP + FRONT)


def wall_texture():
    from PIL import Image, ImageDraw
    w, h, s = 256, 96, 4
    img = Image.new("RGBA", (w * s, h * s), (92, 128, 170, 255))
    d = ImageDraw.Draw(img)
    # panel seams
    for y in (0, h // 2):
        d.rectangle((0, y * s, w * s, y * s + 2 * s), fill=(70, 100, 140, 255))
    for x in range(0, w, 64):
        off = 32 if (x // 64) % 2 else 0
        d.rectangle(((x + off) * s, 0, (x + off) * s + 2 * s, h * s), fill=(76, 108, 150, 255))
    # two painted down arrows
    for cx in (52, 204):
        cx *= s
        top, mid, bot = 24 * s, 56 * s, 78 * s
        d.rectangle((cx - 7 * s, top, cx + 7 * s, mid), fill=(235, 235, 240, 255))
        d.polygon([(cx - 18 * s, mid), (cx + 18 * s, mid), (cx, bot)], fill=(235, 235, 240, 255))
    return img.resize((w, h), Image.LANCZOS)


def hazard_texture():
    from PIL import Image, ImageDraw
    w, h, s = 128, 32, 4
    img = Image.new("RGBA", (w * s, h * s), (225, 40, 40, 255))
    d = ImageDraw.Draw(img)
    for x in range(-h, w + h, 16):
        d.polygon([(x * s, h * s), ((x + 8) * s, h * s), ((x + 8 + h) * s, 0), ((x + h) * s, 0)],
                  fill=(250, 240, 230, 255))
    return img.resize((w, h), Image.LANCZOS)


def ledge_texture():
    from PIL import Image, ImageDraw
    w, h = 64, 16
    img = Image.new("RGBA", (w, h), (150, 150, 158, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w, 2), fill=(200, 200, 210, 255))
    return img


def marker_texture():
    from PIL import Image
    return Image.new("RGBA", (16, 8), (0, 255, 80, 255))


def marker_model():
    """A thin bright bar centred on x, top edge at y=0 (the REL puts it at a player's computed head top)."""
    v, st, f = [], [], []
    w, h = 40.0, 4.0
    _quad(v, st, f, [(-w, -h, 0.0), (w, -h, 0.0), (w, 0.0, 0.0), (-w, 0.0, 0.0)], 1)
    return hsf_build.assemble("ccmark", v, st, f, _normals(), marker_texture(), (-w, -h, -1.0, w, 0.0, 1.0))


def _quad(vertices, st, faces, corners, normal):
    """Append a quad (corners in counter-clockwise order seen from its front) as two faces."""
    base = len(vertices)
    vertices.extend(corners)
    st.extend([(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)])
    faces.extend([(base, base + 1, base + 2, normal), (base, base + 2, base + 3, normal)])


def wall_model():
    """One upright tile, x centred, from y=0 to WALL_TILE_H, at z=0 (the REL places it at WALL_Z)."""
    v, st, f = [], [], []
    w = WALL_W / 2
    _quad(v, st, f, [(-w, 0.0, 0.0), (w, 0.0, 0.0), (w, WALL_TILE_H, 0.0), (-w, WALL_TILE_H, 0.0)], 1)
    return hsf_build.assemble("ccwall", v, st, f, _normals(), wall_texture(), (-w, 0.0, -1.0, w, WALL_TILE_H, 1.0))


def slab_model(name, width, back_z, front_z, depth, image):
    """A slab whose top is at y=0: top face plus front face."""
    v, st, f = [], [], []
    w = width / 2
    _quad(v, st, f, [(-w, 0.0, front_z), (w, 0.0, front_z), (w, 0.0, back_z), (-w, 0.0, back_z)], 0)
    _quad(v, st, f, [(-w, -depth, front_z), (w, -depth, front_z), (w, 0.0, front_z), (-w, 0.0, front_z)], 1)
    return hsf_build.assemble(name, v, st, f, _normals(), image, (-w, -depth, back_z, w, 0.0, front_z))


def models():
    """{saf file index: HSF bytes}"""
    out = {
        FILE_WALL: wall_model(),
        # back edge in the players' plane (z = 0): the top edge of the stripes on screen is exactly the crash line
        FILE_FLOOR: slab_model("ccfloor", FLOOR_W, 0.0, FLOOR_FRONT_Z, FLOOR_DEPTH, hazard_texture()),
        FILE_LEDGE: slab_model("ccledge", LEDGE_W, WALL_Z, LEDGE_FRONT_Z, LEDGE_DEPTH, ledge_texture()),
        FILE_MARKER: marker_model(),
    }
    for blob in out.values():
        hsf_build.check(blob)
    return out


INSTPIC_OVERRIDE = ASSETS / "closecall_instpic.png"


def instpic_image():
    """256x256 instruction picture. Drop a 256x256 screenshot at tools/assets/closecall_instpic.png to use it
    instead of this drawn placeholder."""
    from PIL import Image
    if INSTPIC_OVERRIDE.exists():
        return Image.open(INSTPIC_OVERRIDE).convert("RGBA").resize((256, 256), Image.LANCZOS)
    return draw_scene([(150, "stop"), (196, "stop"), (120, "stop"), (FLOOR_PX, "crash")], dashes=True).convert("RGBA")


FLOOR_PX = 214  # floor line in the 256x256 picture
COLOURS = [(230, 40, 40), (40, 170, 60), (240, 200, 40), (120, 70, 190)]
_BACKDROP = {}


def _backdrop(s):
    from PIL import Image, ImageDraw
    if s not in _BACKDROP:
        big = 256 * s
        img = Image.new("RGBA", (big, big), (0, 0, 0, 255))
        wall = wall_texture().resize((big, big * 96 // 256), Image.LANCZOS)
        for y in range(0, big, wall.size[1]):
            img.paste(wall, (0, y))
        floor_top = FLOOR_PX * s
        img.paste(hazard_texture().resize((big, (256 - FLOOR_PX) * s)), (0, floor_top))
        ImageDraw.Draw(img).rectangle((0, floor_top - 2 * s, big, floor_top), fill=(255, 255, 255, 255))
        _BACKDROP[s] = img
    return _BACKDROP[s].copy()


def draw_scene(players, dashes=False, winner=None, s=4):
    """players: [(head_y in 0..256, "fall" | "stop" | "crash")] for the four columns, drawn upside down.
    dashes: dashed line from each stopped head to the floor. winner: column index that gets sparkles."""
    import math
    from PIL import Image, ImageDraw
    img = _backdrop(s)
    d = ImageDraw.Draw(img)
    floor_top = FLOOR_PX * s
    for i, (head_y, state) in enumerate(players):
        cx = (40 + 58 * i) * s
        hy = int(head_y * s)
        d.rectangle((cx - 9 * s, hy - 40 * s, cx + 9 * s, hy - 12 * s), fill=COLOURS[i] + (255,))       # body
        d.rectangle((cx - 8 * s, hy - 62 * s, cx - 2 * s, hy - 40 * s), fill=(40, 60, 160, 255))     # legs
        d.rectangle((cx + 2 * s, hy - 62 * s, cx + 8 * s, hy - 40 * s), fill=(40, 60, 160, 255))
        d.ellipse((cx - 13 * s, hy - 24 * s, cx + 13 * s, hy + 2 * s), fill=(250, 210, 170, 255),
                  outline=(60, 40, 30, 255), width=2 * s)
        if state == "stop" and dashes:
            for y in range(hy + 6 * s, floor_top - 4 * s, 10 * s):
                d.rectangle((cx - s, y, cx + s, y + 5 * s), fill=(255, 255, 255, 255))
        elif state == "crash":
            for k in range(5):
                a = math.radians(-90 + 72 * k)
                px, py = cx + math.cos(a) * 22 * s, hy - 8 * s + math.sin(a) * 22 * s
                d.regular_polygon((px, py, 6 * s), 5, fill=(255, 240, 80, 255))
        if winner == i:
            for k in range(3):
                a = math.radians(-150 + 60 * k)
                px, py = cx + math.cos(a) * 30 * s, hy - 70 * s + math.sin(a) * 12 * s
                d.regular_polygon((px, py, 7 * s), 4, rotation=45, fill=(255, 250, 150, 255))
    return img.resize((256, 256), Image.LANCZOS).convert("RGB")


PREVIEW_FPS = 25
PREVIEW_STOPS = [150, 196, 120, None]  # head heights where each column stops; None = crashes
PREVIEW_WINNER = 1


def preview_frames():
    """Free Play preview: everyone falls from the top, three stop, one crashes, the closest sparkles."""
    start, speed = 20.0, 1.5
    frames = []
    y = start
    hold = 0
    while True:
        players = []
        done = True
        for stop in PREVIEW_STOPS:
            if stop is not None and y >= stop:
                players.append((stop, "stop"))
            elif stop is None and y >= FLOOR_PX:
                players.append((FLOOR_PX, "crash"))
            else:
                players.append((min(y, FLOOR_PX), "fall"))
                done = False
        frames.append(draw_scene(players, dashes=done, winner=PREVIEW_WINNER if done and hold > 10 else None, s=2))
        if done:
            hold += 1
            if hold > 2 * PREVIEW_FPS:
                break
        y += speed
    return frames


def instpic_anm(template_blob):
    """An instruction-picture ANM: the template's header (one 256x256 CMPR bitmap) with our image."""
    from tools.lib import mpdata
    info = mpdata.parse_anm(template_blob)
    bmp = info["bmps"][0]
    if (bmp["w"], bmp["h"], bmp["fmt"]) != (256, 256, 10) or info["banks"] != 1:
        raise RuntimeError("unexpected instruction-picture template")
    data = mpdata.encode_cmpr(instpic_image())
    if len(data) != bmp["size"]:
        raise RuntimeError("CMPR size mismatch")
    blob = bytearray(template_blob)
    blob[bmp["data_o"]:bmp["data_o"] + bmp["size"]] = data
    return bytes(blob)


def write_header():
    HEADER.parent.mkdir(parents=True, exist_ok=True)
    HEADER.write_text("\n".join([
        "/* Generated by tools/closecall/closecall_assets.py. Do not edit. */",
        "#ifndef CLOSECALL_FILES_H",
        "#define CLOSECALL_FILES_H",
        f"#define CLOSECALL_FILE_WALL {FILE_WALL}",
        f"#define CLOSECALL_FILE_FLOOR {FILE_FLOOR}",
        f"#define CLOSECALL_FILE_LEDGE {FILE_LEDGE}",
        f"#define CLOSECALL_FILE_MARKER {FILE_MARKER}",
        f"#define CLOSECALL_WALL_TILE_H {WALL_TILE_H}f",
        f"#define CLOSECALL_WALL_Z {WALL_Z}f",
        "#endif",
        "",
    ]), encoding="ascii")
    return HEADER


if __name__ == "__main__":
    print(write_header())
    for k, blob in models().items():
        print(k, len(blob))
