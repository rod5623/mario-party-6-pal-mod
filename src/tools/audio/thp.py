"""Write video-only THP 1.0 movies (the format of files/movie/*.thp), for minigame previews.

Layout, as in the retail movies (e.g. m616.thp, version 0x10000):
  0x00 header: "THP\\0", version, maxBufferSize, maxAudioSamples, frameRate (f32), numFrames, firstFrameSize,
       movieDataSize, compInfoDataOffset, offsetDataOffset (0), movieDataOffsets, finalFrameDataOffset
  0x30 component info: count, 16 component types (0 video, 1 audio, 0xFF none), then a video info block
       (width, height) per video component
  frames: nextTotalSize, prevTotalSize (the movie loops: the first frame's previous is the last frame), one size
       per component, then the data; every frame is padded to a multiple of 32 bytes.
Each video frame is a baseline JPEG, 4:2:0, with the same markers as the retail frames
(SOI, DQT, SOF0, DHT, SOS ... EOI); PIL's JFIF APP0 segment is removed.
"""
import io
import struct

HEADER_SIZE = 0x30
VERSION = 0x00010000


def jpeg_frame(image, quality=80):
    buf = io.BytesIO()
    image.convert("RGB").save(buf, "JPEG", quality=quality, subsampling=2, optimize=False, progressive=False)
    data = buf.getvalue()
    out = bytearray(data[:2])  # SOI
    i = 2
    while i < len(data):
        marker = data[i + 1]
        if marker == 0xDA:  # SOS: the rest is entropy-coded data up to and including EOI
            length = struct.unpack_from(">H", data, i + 2)[0]
            scan = data[i + 2 + length:-2]
            if b"\xff\xd0" in scan or any(b"\xff" + bytes([m]) in scan for m in range(0xD1, 0xD8)):
                raise RuntimeError("restart markers are not supported")
            # THP scan data is not byte-stuffed: a 0xFF data byte is stored alone (retail frames hold
            # raw 0xFF bytes without the 0x00 JPEG puts after each one)
            out += data[i:i + 2 + length] + scan.replace(b"\xff\x00", b"\xff") + b"\xff\xd9"
            break
        length = struct.unpack_from(">H", data, i + 2)[0]
        if not 0xE0 <= marker <= 0xEF:  # drop APPn
            out += data[i:i + 2 + length]
        i += 2 + length
    if out[-2:] != b"\xff\xd9":
        raise RuntimeError("JPEG does not end with EOI")
    return bytes(out)


def build(images, fps, quality=80):
    width, height = images[0].size
    if width % 16 or height % 16:
        raise ValueError("THP frame size must be a multiple of 16")
    jpegs = [jpeg_frame(im, quality) for im in images]

    def frame_size(j):
        size = 12 + len(j)
        return size + (-size % 32)

    sizes = [frame_size(j) for j in jpegs]
    comp = struct.pack(">I", 1) + bytes([0] + [0xFF] * 15) + struct.pack(">II", width, height)
    first = HEADER_SIZE + len(comp)
    first += -first % 32
    n = len(jpegs)
    body = bytearray()
    for k, j in enumerate(jpegs):
        frame = struct.pack(">III", sizes[(k + 1) % n], sizes[k - 1], len(j)) + j
        body += frame + b"\0" * (sizes[k] - len(frame))
    final = first + sum(sizes[:-1])
    header = struct.pack(">4sIIIfIIIIIII", b"THP\0", VERSION, max(sizes), 0, float(fps), n, sizes[0], len(body),
                         HEADER_SIZE, 0, first, final)
    assert len(header) == HEADER_SIZE
    out = bytearray(header + comp)
    out += b"\0" * (first - len(out))
    return bytes(out + body)
