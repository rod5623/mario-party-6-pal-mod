"""Draw the four Castaway Bay wheel icons (84x84 RGBA) into assets/: python -m tools.scripts.make_castaway_wheel_icons

orb (a glossy purple sphere), +5 (gold coin), -10 (red coin), warp (a cyan swirl). The PNGs are committed, so
apply_castaway_wheel_patch.py does not depend on the fonts of the machine it runs on.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tools.lib.paths import ASSETS
SIZE = 84
SCALE = 4
NAMES = ("orb", "minus10", "warp", "plus10")


def canvas():
    big = SIZE * SCALE
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), big


def finish(img):
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def font(size):
    for name in ("arialbd.ttf", "C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def outlined_text(draw, centre, text, size, fill, outline):
    f = font(size * SCALE)
    x, y = centre
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            if dx * dx + dy * dy <= 9:
                draw.text((x + dx, y + dy), text, font=f, fill=outline, anchor="mm")
    draw.text((x, y), text, font=f, fill=fill, anchor="mm")


def orb():
    img, d, big = canvas()
    m = 4 * SCALE
    d.ellipse((m, m, big - m, big - m), fill=(40, 20, 90, 255))
    for i in range(14):  # sphere shading: shrink towards the lit corner
        t = i / 14
        r = (big - 2 * m) * (1 - 0.55 * t) / 2
        cx = big / 2 - 0.16 * big * t
        cy = big / 2 - 0.16 * big * t
        colour = (int(90 + 130 * t), int(50 + 90 * t), int(170 + 70 * t), 255)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=colour)
    d.ellipse((big * 0.26, big * 0.2, big * 0.46, big * 0.36), fill=(255, 255, 255, 230))
    d.ellipse((m, m, big - m, big - m), outline=(255, 255, 255, 255), width=3 * SCALE)
    return finish(img)


def coin(text, face, rim, ink):
    img, d, big = canvas()
    m = 4 * SCALE
    d.ellipse((m, m, big - m, big - m), fill=rim + (255,))
    d.ellipse((m + 5 * SCALE, m + 5 * SCALE, big - m - 5 * SCALE, big - m - 5 * SCALE), fill=face + (255,))
    d.arc((m + 9 * SCALE, m + 9 * SCALE, big - m - 9 * SCALE, big - m - 9 * SCALE), 200, 290, fill=(255, 255, 255, 200), width=2 * SCALE)
    d.ellipse((m, m, big - m, big - m), outline=(255, 255, 255, 255), width=3 * SCALE)
    outlined_text(d, (big / 2, big / 2 + 2 * SCALE), text, 27 if len(text) < 3 else 22, ink, (255, 255, 255, 255))
    return finish(img)


def warp():
    img, d, big = canvas()
    m = 4 * SCALE
    d.ellipse((m, m, big - m, big - m), fill=(10, 60, 110, 255))
    cx = cy = big / 2
    points = []
    for i in range(0, 260):
        a = i * 0.075
        r = (3 + i * 0.145) * SCALE * 0.95
        points.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.line(points, fill=(120, 240, 255, 255), width=6 * SCALE, joint="curve")
    d.ellipse((cx - 5 * SCALE, cy - 5 * SCALE, cx + 5 * SCALE, cy + 5 * SCALE), fill=(255, 255, 255, 255))
    d.ellipse((m, m, big - m, big - m), outline=(255, 255, 255, 255), width=3 * SCALE)
    return finish(img)


def main():
    icons = {
        "orb": orb(),
        "plus10": coin("+10", (255, 215, 60), (200, 140, 20), (140, 80, 0, 255)),
        "minus10": coin("-10", (235, 80, 70), (170, 30, 40), (130, 10, 20, 255)),
        "warp": warp(),
    }
    for name, image in icons.items():
        image.save(ASSETS / f"castaway_wheel_icon_{name}.png")
    sheet = Image.new("RGBA", (SIZE * 4 + 40, SIZE + 20), (60, 120, 70, 255))
    for k, name in enumerate(NAMES):
        sheet.paste(icons[name], (10 + k * (SIZE + 3), 10), icons[name])
    sheet.save(Path(__import__("sys").argv[1])) if len(__import__("sys").argv) > 1 else None
    print("wrote", ", ".join(f"castaway_wheel_icon_{n}.png" for n in NAMES))


if __name__ == "__main__":
    main()
