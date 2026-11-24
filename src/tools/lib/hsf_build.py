"""Build the Castaway Bay floating wheel model: python -m tools.lib.hsf_build [out.hsf [preview.png]]

A small static HSF V037 model (the board-model format of capsule.bin entries): a thin vertical disc, textured
with a 4-slice pie wheel (gold, green, purple, red), both faces drawn. The file layout follows the loader
(mp6-repo src/game/hsfload.c): a header of 21 (offset, count) sections, then in-place structures whose pointers
are indices into the string/symbol tables. Structure sizes (material 0x3C, attribute 0x84, object 0x144, bitmap
0x20, face 0x30) were read from the Soluna orb model (assets/mp6dx_soluna_orb.hsf), which this reuses as a
template for the fields that are not understood (attribute and material bodies).

No skeleton (cenv 0) means the normals are s8 triples (hsfdraw.c, GXSetArray(GX_VA_NRM, ..., 3 * sizeof(s8))).
"""
import math
import struct
import sys
from pathlib import Path

from tools.lib import mpdata

from tools.lib.paths import TOOLS
TEMPLATE = TOOLS / "assets" / "mp6dx_soluna_orb.hsf"

RADIUS = 40.0
HALF_THICKNESS = 0.6
SEGMENTS = 32
TEX = 128
SECTIONS = (
    "scene color material attribute vertex normal st face object bitmap palette motion cenv skeleton part "
    "cluster shape mapAttr matrix symbol string"
).split()
SLICE_COLOURS = ((255, 200, 40), (60, 200, 90), (120, 60, 170), (220, 50, 50))  # top, right, bottom, left


def texture():
    """128x128 RGBA pie: four 90-degree slices centred on the axes, white spokes, rim and hub."""
    from PIL import Image, ImageDraw
    scale = 4
    size = TEX * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    box = (2 * scale, 2 * scale, size - 2 * scale, size - 2 * scale)
    # PIL angles run clockwise from 3 o'clock; slice k is centred k * 90 degrees clockwise from the top
    for k, colour in enumerate(SLICE_COLOURS):
        centre = -90 + 90 * k
        draw.pieslice(box, centre - 45, centre + 45, fill=colour + (255,))
    for k in range(4):  # spokes between the slices
        angle = math.radians(-45 + 90 * k)
        cx = cy = size / 2
        draw.line((cx, cy, cx + math.cos(angle) * size / 2, cy + math.sin(angle) * size / 2),
                  fill=(255, 255, 255, 255), width=3 * scale)
    draw.ellipse(box, outline=(255, 255, 255, 255), width=5 * scale)
    hub = size * 0.09
    draw.ellipse((size / 2 - hub, size / 2 - hub, size / 2 + hub, size / 2 + hub), fill=(255, 255, 255, 255))
    return img.resize((TEX, TEX), Image.LANCZOS)


class Strings:
    def __init__(self):
        self.data = bytearray()
        self.index = {}

    def add(self, text):
        if text not in self.index:
            self.index[text] = len(self.data)
            self.data += text.encode("ascii") + b"\0"
        return self.index[text]


def align(buf, to=4):
    buf += b"\0" * (-len(buf) % to)


def build(texture_image=None):
    """The wheel: a thin disc, both faces textured with the pie."""
    # geometry: front disc at +z, back disc at -z with mirrored u; vertex 0 = centre, 1..N = rim
    vertices, st = [], []
    for z, mirror in ((HALF_THICKNESS, False), (-HALF_THICKNESS, True)):
        vertices.append((0.0, 0.0, z))
        st.append((0.5, 0.5))
        for i in range(SEGMENTS):
            a = 2 * math.pi * i / SEGMENTS
            vertices.append((RADIUS * math.cos(a), RADIUS * math.sin(a), z))
            u = 0.5 + 0.5 * math.cos(a)
            st.append((1.0 - u if mirror else u, 0.5 - 0.5 * math.sin(a)))
    ring = SEGMENTS + 1
    faces = []
    for i in range(SEGMENTS):
        j = (i + 1) % SEGMENTS
        faces.append((0, 1 + i, 1 + j, 0))                         # front, normal +z (index 0)
    for i in range(SEGMENTS):
        j = (i + 1) % SEGMENTS
        faces.append((ring, ring + 1 + j, ring + 1 + i, 1))        # back, normal -z (index 1)
    normals = bytes([0, 0, 127, 0, 0, 0x81])
    image = texture_image if texture_image is not None else texture()
    bounds = (-RADIUS, -RADIUS, -HALF_THICKNESS, RADIUS, RADIUS, HALF_THICKNESS)
    return assemble("wheel", vertices, st, faces, normals, image, bounds)


def build_card(image, width, height, name="card"):
    """A flat upright card (x across, y up, feet at the origin), drawn from both sides and turned to face the
    camera by the renderer (object flag HSF_MATERIAL_BBOARD). image: RGBA, sides multiples of 8; pixels with
    alpha below 128 are cut out."""
    w = width / 2
    vertices = [(-w, 0.0, 0.0), (w, 0.0, 0.0), (w, height, 0.0), (-w, height, 0.0)]
    st = [(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)]
    faces = [(0, 1, 2, 0), (0, 2, 3, 0)]  # NOCULL draws the back too, and the billboard keeps the front to us
    normals = bytes([0, 0, 127, 0, 0, 0x81])
    bounds = (-w, 0.0, -1.0, w, height, 1.0)
    return assemble(name, vertices, st, faces, normals, image, bounds, flags=HSF_BBOARD)


HSF_BBOARD = 1  # HSF_MATERIAL_BBOARD in the object flags (hsfformat.h; hsfdraw.c faces the object to the camera)


def assemble(name, vertices, st, faces, normals, image, bounds, flags=0):
    """One textured mesh object under a root object. faces: (a, b, c, normal index) triangles."""
    template = TEMPLATE.read_bytes()
    t_off = {n: struct.unpack_from(">II", template, 8 + 8 * i)[0] for i, n in enumerate(SECTIONS)}
    strings = Strings()
    s_wheel, s_root = strings.add(name), strings.add(f"{name}_root")
    s_mat, s_vtx, s_tex = strings.add(f"{name}_mat"), strings.add(f"{name}_vtx"), strings.add(f"{name}_tex")

    out = bytearray(0xB0)
    out[0:8] = b"HSFV037\0"
    sections = {}

    def put(name, count, blob):
        align(out)
        sections[name] = (len(out), count)
        out.extend(blob)

    put("scene", 1, template[t_off["scene"]:t_off["scene"] + 0x10])

    material = bytearray(template[t_off["material"]:t_off["material"] + 0x3C])
    struct.pack_into(">I", material, 0, s_mat)
    material[0x0B:0x0E] = b"\xff\xff\xff"                     # litColor: no darkening of the texture
    struct.pack_into(">I", material, 0x30, 0x2)               # HSF_MATERIAL_NOCULL
    struct.pack_into(">II", material, 0x34, 1, 0)             # one attribute, symbol-table index 0
    put("material", 1, material)

    attribute = bytearray(template[t_off["attribute"]:t_off["attribute"] + 0x84])
    struct.pack_into(">I", attribute, 0, 0xFFFFFFFF)          # unnamed
    struct.pack_into(">i", attribute, 0x80, 0)                # bitmap 0
    put("attribute", 1, attribute)

    def buffer(name, count, data):
        header = struct.pack(">IiI", s_vtx, count, 0)
        put(name, 1, header + data)

    buffer("vertex", len(vertices), b"".join(struct.pack(">3f", *v) for v in vertices))
    buffer("normal", 2, normals + b"\0\0")
    buffer("st", len(st), b"".join(struct.pack(">2f", *p) for p in st))

    face_blob = bytearray()
    for a, b, c, normal in faces:
        indices = [(a, normal, -1, a), (b, normal, -1, b), (c, normal, -1, c), (0, 0, 0, 0)]
        face_blob += struct.pack(">hh", 2, 0)
        face_blob += b"".join(struct.pack(">4h", *i) for i in indices)
        face_blob += struct.pack(">3f", 0.0, 0.0, 0.0)
    assert len(face_blob) == 0x30 * len(faces)
    buffer("face", len(faces), bytes(face_blob))

    def obj(label, kind, parent, child_count, child_index, mesh):
        o = bytearray(0x144)
        struct.pack_into(">IIII", o, 0, label, kind, 0, flags if mesh else 0)
        struct.pack_into(">iII", o, 16, parent, child_count, child_index)
        struct.pack_into(">9f", o, 28, 0, 0, 0, 0, 0, 0, 1, 1, 1)          # base transform
        struct.pack_into(">9f", o, 64, 0, 0, 0, 0, 0, 0, 1, 1, 1)          # curr transform
        struct.pack_into(">i", o, 256, -1)
        struct.pack_into(">i", o, 272, -1)                                  # no vertex colours
        struct.pack_into(">i", o, 296, -1)
        struct.pack_into(">i", o, 312, -1)                                  # no cenv
        if mesh:
            struct.pack_into(">6f", o, 100, *bounds)
            struct.pack_into(">5i", o, 260, 0, 0, 0, -1, 0)                 # face, vertex, normal, colour, st
            struct.pack_into(">ii", o, 280, 0, 0)                           # material 0, attribute 0
        return o

    # object 0 = the mesh (child of object 1), object 1 = the root (no parent, one child, symbol index 1)
    put("object", 2, obj(s_wheel, 2, 1, 0, 0, True) + obj(s_root, 0, -1, 1, 1, False))

    tex_w, tex_h = image.size
    bitmap_data = mpdata.encode_cmpr(image)
    align(out, 4)
    headers_end = len(out) + 0x20
    pad = -(headers_end + 4) % 32 + 4                     # texture data must start on a 32-byte boundary
    # name, maxLod, format 7 (CMPR), pixSize 8, width, height, palSize, tint, palData (-1 = none), unused, data offset
    header = struct.pack(">IIBBhhhIiII", s_tex, 1, 7, 8, tex_w, tex_h, 0, 0, -1, 0, pad)
    assert len(header) == 0x20
    put("bitmap", 1, header)
    out += b"\0" * pad
    out += bitmap_data

    put("symbol", 2, struct.pack(">2I", 0, 0))            # [0] attribute list of the material, [1] child list
    align(out)
    sections["string"] = (len(out), len(strings.data))
    out.extend(strings.data)
    align(out)

    end = len(out)
    for name in SECTIONS:
        offset, count = sections.get(name, (end, 0))
        struct.pack_into(">II", out, 8 + 8 * SECTIONS.index(name), offset, count)
    return bytes(out)


def check(blob):
    """Re-do the loader's pointer arithmetic and make sure every offset lies inside the file."""
    names = SECTIONS
    head = {n: struct.unpack_from(">II", blob, 8 + 8 * i) for i, n in enumerate(names)}
    size = len(blob)
    string = head["string"][0]
    for n, (offset, count) in head.items():
        assert 0 <= offset <= size, n
    def string_at(ofs):
        assert string + ofs < size
        return blob[string + ofs:blob.index(b"\0", string + ofs)].decode()
    # buffers
    for n in ("vertex", "normal", "st", "face"):
        offset, count = head[n]
        base = offset + 12 * count
        for k in range(count):
            nm, c, data = struct.unpack_from(">IiI", blob, offset + 12 * k)
            string_at(nm)
            stride = {"vertex": 12, "normal": 3, "st": 8, "face": 0x30}[n]
            assert base + data + c * stride <= size, (n, k)
    # objects
    offset, count = head["object"]
    roots = 0
    symbols = struct.unpack_from(f">{head['symbol'][1]}I", blob, head["symbol"][0])
    for i in range(count):
        o = offset + 0x144 * i
        name, kind = struct.unpack_from(">II", blob, o)
        string_at(name)
        parent, children, child = struct.unpack_from(">iII", blob, o + 16)
        roots += parent == -1
        for k in range(children):
            assert symbols[child + k] < count
        if kind == 2:
            face, vtx, nrm, col, st = struct.unpack_from(">5i", blob, o + 260)
            assert 0 <= face < head["face"][1] and 0 <= vtx < head["vertex"][1]
            assert 0 <= nrm < head["normal"][1] and 0 <= st < head["st"][1]
    assert roots == 1
    # faces index into the mesh buffers
    offset, count = head["face"]
    nm, faces, data = struct.unpack_from(">IiI", blob, offset)
    base = offset + 12 + data
    nverts, nst = struct.unpack_from(">i", blob, head["vertex"][0] + 4)[0], struct.unpack_from(">i", blob, head["st"][0] + 4)[0]
    for k in range(faces):
        kind, mat = struct.unpack_from(">hh", blob, base + 0x30 * k)
        assert kind == 2 and mat == 0
        for v in range(3):
            vertex, normal, colour, tex = struct.unpack_from(">4h", blob, base + 0x30 * k + 4 + 8 * v)
            assert 0 <= vertex < nverts and 0 <= normal < 2 and colour == -1 and 0 <= tex < nst
    # bitmap
    offset, count = head["bitmap"]
    nm, lod, fmt, pix, w, h, pal = struct.unpack_from(">IIBBhhh", blob, offset)
    data = struct.unpack_from(">I", blob, offset + 0x1C)[0]
    start = offset + 0x20 * count + data
    assert start % 32 == 0 and start + w * h // 2 <= size and fmt == 7
    return head


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else TOOLS / "assets" / "castaway_wheel.hsf"
    blob = build()
    check(blob)
    out.write_bytes(blob)
    print(f"{out}: {len(blob)} bytes")
    if len(sys.argv) > 2:
        texture().save(sys.argv[2])


if __name__ == "__main__":
    main()
