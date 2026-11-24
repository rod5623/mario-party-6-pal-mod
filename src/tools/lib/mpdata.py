"""Reading and writing Mario Party 6 data archives (data/*.bin) and their sprite (ANM) files.

Archive: u32 count, u32 offsets[count]; each file at its offset is
  u32 decoded size, u32 decode type (7 = zlib), then for zlib u32 decoded size, u32 compressed size, data.
Sprite files (see include/game/animdata.h): ANIMDATA header, banks, patterns, layers and
bitmaps; image data is usually GameCube CMPR (DXT1-like, 8x8 tiles of four 4x4 blocks).
"""
import struct
import zlib

TYPE_NONE = 0
TYPE_ZLIB = 7


def read_archive(path):
    data = open(path, "rb").read()
    count = struct.unpack_from(">I", data, 0)[0]
    offsets = list(struct.unpack_from(">%dI" % count, data, 4))
    return data, offsets


def file_bounds(data, offsets, index):
    end = offsets[index + 1] if index + 1 < len(offsets) else len(data)
    return offsets[index], end


def read_file(data, offsets, index):
    start, end = file_bounds(data, offsets, index)
    size, kind = struct.unpack_from(">II", data, start)
    if kind == TYPE_NONE:
        return data[start + 8:start + 8 + size]
    if kind == TYPE_ZLIB:
        compressed = struct.unpack_from(">I", data, start + 12)[0]
        return zlib.decompress(data[start + 16:start + 16 + compressed])
    raise ValueError(f"file {index}: unsupported decode type {kind}")


def pack_file(payload):
    compressed = zlib.compress(payload, 9)
    blob = struct.pack(">IIII", len(payload), TYPE_ZLIB, len(payload), len(compressed)) + compressed
    return blob + b"\0" * (-len(blob) % 4)


def append_files(data, offsets, payloads):
    """Return a new archive with payloads appended as new files (indices len(offsets)...)."""
    count = len(offsets)
    new_count = count + len(payloads)
    shift = 4 * len(payloads)
    body = data[4 + 4 * count:]
    out_offsets = [o + shift for o in offsets]
    position = len(data) + shift
    extra = b""
    for payload in payloads:
        blob = pack_file(payload)
        out_offsets.append(position)
        position += len(blob)
        extra += blob
    header = struct.pack(">I", new_count) + struct.pack(">%dI" % new_count, *out_offsets)
    return header + body + extra, out_offsets


def parse_anm(blob):
    bank_n, pat_n, bmp_n, _ = struct.unpack_from(">hhhh", blob, 0)
    bank_o, pat_o, bmp_o = struct.unpack_from(">III", blob, 8)
    bmps = []
    for i in range(bmp_n):
        pix, fmt, pal, sx, sy, dsize, pal_o, data_o = struct.unpack_from(">BBhhhIII", blob, bmp_o + 20 * i)
        bmps.append(dict(pix=pix, fmt=fmt & 0xF, pal=pal, w=sx, h=sy, size=dsize, pal_o=pal_o, data_o=data_o))
    return dict(banks=bank_n, pats=pat_n, bmps=bmps, bmp_o=bmp_o)


def _rgb565(v):
    r = (v >> 11) & 31
    g = (v >> 5) & 63
    b = v & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def decode_cmpr(data, w, h):
    from PIL import Image
    img = Image.new("RGBA", (w, h))
    px = img.load()
    pos = 0
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for by in range(2):
                for bx in range(2):
                    c0, c1 = struct.unpack_from(">HH", data, pos)
                    idx = struct.unpack_from(">I", data, pos + 4)[0]
                    pos += 8
                    p0, p1 = _rgb565(c0), _rgb565(c1)
                    pal = [p0 + (255,), p1 + (255,)]
                    if c0 > c1:
                        pal.append(tuple((2 * a + b) // 3 for a, b in zip(p0, p1)) + (255,))
                        pal.append(tuple((a + 2 * b) // 3 for a, b in zip(p0, p1)) + (255,))
                    else:
                        pal.append(tuple((a + b) // 2 for a, b in zip(p0, p1)) + (255,))
                        pal.append((0, 0, 0, 0))
                    for y in range(4):
                        for x in range(4):
                            shift = 30 - 2 * (4 * y + x)
                            px[tx + bx * 4 + x, ty + by * 4 + y] = pal[(idx >> shift) & 3]
    return img


def _to565(rgb):
    r, g, b = rgb
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def _principal_endpoints(colors):
    """Two RGB endpoints along the principal axis of the colours."""
    n = len(colors)
    mean = [sum(c[k] for c in colors) / n for k in range(3)]
    cov = [[sum((c[i] - mean[i]) * (c[j] - mean[j]) for c in colors) for j in range(3)] for i in range(3)]
    axis = [1.0, 1.0, 1.0]
    for _ in range(8):
        axis = [sum(cov[i][j] * axis[j] for j in range(3)) for i in range(3)]
        norm = sum(a * a for a in axis) ** 0.5
        if norm == 0:
            break
        axis = [a / norm for a in axis]
    projected = sorted(colors, key=lambda c: sum((c[k] - mean[k]) * axis[k] for k in range(3)))
    return projected[0], projected[-1]


def encode_cmpr_block(block):
    """Encode one 4x4 block (16 RGBA tuples, row-major) as 8 CMPR bytes."""
    opaque = [p[:3] for p in block if p[3] >= 128]
    has_clear = len(opaque) != 16
    if not opaque:
        return struct.pack(">HHI", 0, 0, 0xFFFFFFFF)
    lo, hi = _principal_endpoints(opaque)
    c0, c1 = _to565(lo), _to565(hi)
    if has_clear:
        if c0 > c1:
            c0, c1 = c1, c0
        p0, p1 = _rgb565(c0), _rgb565(c1)
        pal = [p0, p1, tuple((a + b) // 2 for a, b in zip(p0, p1))]
    else:
        if c0 == c1:
            return struct.pack(">HHI", c0, c1, 0)
        if c0 < c1:
            c0, c1 = c1, c0
        p0, p1 = _rgb565(c0), _rgb565(c1)
        pal = [p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)), tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))]
    indices = 0
    for k, pixel in enumerate(block):
        if pixel[3] < 128:
            choice = 3
        else:
            choice = min(range(len(pal)), key=lambda n: sum((c - q) ** 2 for c, q in zip(pixel[:3], pal[n])))
        indices |= choice << (30 - 2 * k)
    return struct.pack(">HHI", c0, c1, indices)


def encode_cmpr(img, keep=None):
    """Encode an RGBA PIL image (size multiple of 8) as CMPR.

    keep: optional (raw_bytes, predicate(bx, by) -> bool); blocks (4x4 grid) for which the
    predicate is true are copied from raw_bytes (a CMPR stream of the same size) unchanged.
    """
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    out = bytearray()
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            for by in range(2):
                for bx in range(2):
                    x0, y0 = tx + bx * 4, ty + by * 4
                    if keep and keep[1](x0 // 4, y0 // 4):
                        pos = len(out)
                        out += keep[0][pos:pos + 8]
                        continue
                    block = [px[x0 + x, y0 + y] for y in range(4) for x in range(4)]
                    out += encode_cmpr_block(block)
    return bytes(out)
