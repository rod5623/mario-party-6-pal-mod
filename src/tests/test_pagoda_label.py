"""tools.pagoda.label: Pagoda Peak's results label, built into MP6's label sprite."""
from PIL import Image, ImageDraw

from tools.pagoda import label


def labels(count):
    out = []
    for i in range(count):
        img = Image.new("RGB", (label.W, label.H), (20 * i, 100, 200))
        img.putpixel((i, i), (255, 255, 255))
        out.append(img)
    return out


TEMPLATE = {
    "use": 0,
    "pats": [(1, 68, 20, 136, 40, 0, 0)],
    "layers": [(255, 0, 0, 0, 0, 136, 40, 0, 0, 0, 0, 136, 0, 136, 40, 0, 40)],
    "banks": [(1, 0, 0)],
    "frames": [(0, 0, 0, 0, 0, 0)],
    "bmp": (16, 1, 0, 136, 40, 0, 0, 0),
}


def test_build_and_read_round_trip():
    blob = label.build_sprite(TEMPLATE, labels(7))
    sprite = label.read_sprite(blob)
    label.check_layout(sprite)
    assert len(sprite["banks"]) == 7
    for i, img in enumerate(labels(7)):
        got = label.bank_image(sprite, i).convert("RGB")
        assert got.getpixel((i, i)) == (255, 255, 255)
        r, g, b = img.getpixel((100, 30))
        expand5, expand6 = (lambda v: (v >> 3 << 3) | (v >> 5)), (lambda v: (v >> 2 << 2) | (v >> 6))
        assert got.getpixel((100, 30)) == (expand5(r), expand6(g), expand5(b))   # RGB565 rounding


def words_image(gap):
    img = Image.new("RGBA", (60, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 25, 9), fill=(255, 128, 0, 255))
    draw.rectangle((26 + gap, 0, 59, 9), fill=(255, 128, 0, 255))
    return img


def test_split_words_at_a_space():
    words = label.split_words(words_image(3))
    assert len(words) == 2 and words[0].width == 26


def test_one_word_stays_whole():
    assert len(label.split_words(words_image(0))) == 1


def test_blank_pill_clears_inside_the_ring():
    pill = Image.new("RGB", (label.W, label.H), (230, 117, 255))
    draw = ImageDraw.Draw(pill)
    draw.rounded_rectangle((2, 2, label.W - 3, label.H - 3), radius=16, outline=(255, 255, 255), width=2)
    draw.rectangle((50, 15, 80, 25), fill=(10, 200, 10))      # lettering
    out = label.blank_pill(pill)
    assert out.getpixel((60, 20)) == (230, 117, 255)
    assert out.getpixel((label.W // 2, 2)) == (255, 255, 255)
