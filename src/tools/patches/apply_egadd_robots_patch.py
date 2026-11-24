"""E. Gadd's Garage: two cigar-smoking robots, each with the spare change guy's event (for now).

Same design as apply_castaway_spare_change_patch.py (see boards/castaway bay/castaway-bay.md):
  * Two pass-only nodes appended to w02.bin / w02n.bin: 114 between 82 and 83 (top pipe row) and 115 between 95
    and 113 (round platform by the crane). Kind 0, type 0, flag 0x400000, one link; 82 and 95 now link to them.
    Kind 0 never counts as a step and cannot end a move, so the event only fires when walking past.
  * The robot card (boards/E. Gadd's Garage/robot.jpeg, cut out to assets/egadd_robot.png) is file 58 of both
    archives (data 0xE5003A day / 0xE6003A night); two models from it are created at board init, beside the
    spaces the user marked (ROBOT_POS).
  * Event (identical to the spare change guy, lines and rewards included): "Spare change?" Yes/No, pay 5 coins,
    then an orb (Mushroom / Super 'Shroom / Paratroopa; no Boo-away, unlike Castaway) / 20 coins back / asked again / nothing / everyone else pays up to 5. No speaker face.
  * Hooks, chained onto the E. Gadd wheel's (apply_egadd_wheel_patch.py):
      .text 0x3A0C (pass entry of fn_1_39F4; was the wheel's pass cave) -> CAVE_PASS: the wheel's pass cave first
          (it does the displaced `mr r29,r4`), then the event when the space has flag 0x400000;
      .text 0x1B44 (init tail; was the wheel's init cave) -> CAVE_INIT: the wheel's init cave (wheel model and the
          original mbMapCameraSet call), then the two robot cards.
  * Code: copies of the spare change show / ask / event caves (bank 0x30, records 34-42) in DOL section 17 after
    the Orb Morpher (apply_egadd_morpher_patch.py).
  * Text: bank 0x30 records 34-42, the spare change guy's lines, English in every language file.

Run after apply_egadd_morpher_patch.py. Idempotent. Not run in Dolphin.
"""
import shutil
import struct
from collections import deque

from tools.patches import apply_castaway_spare_change_patch as spare
from tools.patches import apply_egadd_calamity_patch as cal
from tools.patches import apply_egadd_morpher_patch as morph
from tools.patches import apply_egadd_wheel_patch as egw
from tools.patches import apply_wheel_of_fortune_patch as wheel
from tools.lib import hsf_build
from tools.lib import mpdata
from tools.lib.paths import DOL
from tools.lib.dol import dol_offset
from tools.lib.boards import load_spaces, replace_file0
from tools.lib.paths import MESS_NAMES, MESS_OUTPUT_DIR, REL_DIR
from tools.patches.apply_star_shuffle_bet_patch import edit_bank
from tools.lib.ppc import i_li, i_rlwinm
from tools.lib.ppc import Asm, LBZ, i_addi, i_lis, i_mem, i_mr, i_ori, i_slwi, ha, lo
from tools.lib.messages import _bounds
from tools.lib.paths import BACKUPS, GAME_DATA
from tools.lib.ppc import epilogue, i_extsh, prologue
from tools.lib.rel import check_words, import_blocks, retarget_call, walk_relocs

from tools.lib.paths import TOOLS
SOURCE_ART = TOOLS.parent.parent / "boards" / "E. Gadd's Garage" / "robot.jpeg"
ART = TOOLS / "assets" / "egadd_robot.png"
REL_NAME = egw.REL_NAME
BOARDS = ("w02", "w02n")

# the trigger nodes: (new id, from, to, position = midpoint of from and to)
VANILLA_SPACES = 113
NODES = ((114, 82, 83, (-1026.5, 1164.0, -5054.0)),
         (115, 95, 113, (-3344.0, 568.5, -1286.5)))
NODE_FLAG = 0x400000            # unused on w02 and not in mbBranchMAttrSet(0x502)

# the cards
CARD_FILE = 58                  # w02.bin / w02n.bin have 58 files
DIR_DAY, DIR_NIGHT = 0xE5, 0xE6
ROBOT_WIDTH, ROBOT_HEIGHT = 156.0, 312.0   # the tax man's size (spare change guy 130 x 260)
# beside the trigger nodes (halfway between the two spaces), set off the path so players don't walk through them.
# First version stood beside spaces 82 / 95 instead (seen in Dolphin 2026-11-06: fine, but not between the spaces).
ROBOT_POS = ((-1026.5, 1164.0, -5210.0),   # node 114 (-1026.5, 1164, -5054), 156 behind it (away from the camera)
             (-3494.0, 568.5, -1286.5))    # node 115 (-3344, 568.5, -1286.5), 150 left of the path 95 -> 113

# the orb outcome draws evenly from this (the spare change guy also has Boo-away, 31; removed for the robots)
ORB_POOL = (0, 1, 25)           # Mushroom, Super 'Shroom, Paratroopa (MP6 has no plain Koopa Troopa orb)

# code: DOL section 17, after the Orb Morpher
CAVE_SHOW = morph.USED_END      # 0x802F8FA0 (0x40)
CAVE_ASK = CAVE_SHOW + 0x40     # (0xA0)
CAVE_PASS = CAVE_ASK + 0xA0     # the .text 0x3A0C hook (0x60)
CAVE_INIT = CAVE_PASS + 0x60    # the .text 0x1B44 hook (0x100)
CAVE_EVENT = CAVE_INIT + 0x100  # (0x280)
CAVE_DATA = CAVE_EVENT + 0x280  # spare change data block (robot A position, hold floats, orb pool), then robot B
USED_END = CAVE_DATA + 0x40
assert USED_END <= morph.CODE_END

# text
BANK = egw.BANK
BANK_RECORDS = cal.BANK_RECORDS  # 34
RECORDS = spare.RECORDS          # the spare change guy's 9 lines (ask, greedy, orb, full, back, more, sucker, steal, broke)
MSGS = tuple(range(BANK_RECORDS, BANK_RECORDS + len(RECORDS)))  # 34-42


# ---- art --------------------------------------------------------------------

def cut_out(path):
    """Remove the white background, the white sticker border and its grey shadow: flood fill from the edges over
    light, low-saturation pixels (stops at the dark outline), drop specks of opaque pixels left by JPEG noise,
    crop to the figure."""
    from PIL import Image
    image = Image.open(path).convert("RGB")
    w, h = image.size
    px = image.load()
    background = bytearray(w * h)
    queue = deque([(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)])
    while queue:
        x, y = queue.popleft()
        i = y * w + x
        if background[i]:
            continue
        c = px[x, y]
        if min(c) < 130 or max(c) - min(c) > 30:
            continue
        background[i] = 1
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not background[ny * w + nx]:
                queue.append((nx, ny))
    # opaque islands smaller than this are noise (the smoke puff is ~2500 px and stays)
    seen = bytearray(background)
    for start in range(w * h):
        if seen[start]:
            continue
        island, queue = [], deque([start])
        seen[start] = 1
        while queue:
            i = queue.popleft()
            island.append(i)
            x, y = i % w, i // w
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                j = ny * w + nx
                if 0 <= nx < w and 0 <= ny < h and not seen[j]:
                    seen[j] = 1
                    queue.append(j)
        if len(island) < 400:
            for i in island:
                background[i] = 1
    out = image.convert("RGBA")
    op = out.load()
    for i in range(w * h):
        if background[i]:
            op[i % w, i // w] = (0, 0, 0, 0)
    return out.crop(out.getbbox())


def card_image():
    from PIL import Image
    if not ART.exists() or ART.stat().st_mtime < SOURCE_ART.stat().st_mtime:
        cut_out(SOURCE_ART).save(ART)
    art = Image.open(ART).convert("RGBA")
    art.thumbnail((spare.CARD_W, spare.CARD_H), Image.LANCZOS)
    image = Image.new("RGBA", (spare.CARD_W, spare.CARD_H), (0, 0, 0, 0))
    image.paste(art, ((spare.CARD_W - art.width) // 2, spare.CARD_H - art.height))  # feet on the bottom edge
    return image


def card_model():
    blob = hsf_build.build_card(card_image(), ROBOT_WIDTH, ROBOT_HEIGHT, name="robot")
    hsf_build.check(blob)
    return blob


# ---- code -------------------------------------------------------------------

def build_pass(address):
    """Called from the start of fn_1_39F4 (r3 = player, r4 = space): the wheel's pass cave (which also does the
    displaced `mr r29,r4`), then the robot event on flag NODE_FLAG."""
    a = Asm(address)
    saved = (30, 31)
    prologue(a, 0x20, saved)
    a.word(i_mr(30, 3))
    a.word(i_mr(31, 4))
    a.call(egw.CAVE_PASS)
    a.word(i_mr(3, 31))
    a.call(spare.FN_FLAGS)
    bit = 31 - (NODE_FLAG.bit_length() - 1)
    a.word(i_rlwinm(0, 3, 0, bit, bit) | 1)
    a.branch("beq", "return")
    a.word(i_mr(3, 30))
    a.call(CAVE_EVENT)
    a.label("return")
    epilogue(a, 0x20, saved)
    return spare.fits(a.assemble(), CAVE_INIT - CAVE_PASS, "pass")


def build_init(address):
    """Replaces the call at .text 0x1B44 (r3/r4/f1 are mbMapCameraSet's arguments): the wheel's init cave (which
    creates the wheel and makes that call), then one robot card per ROBOT_POS."""
    a = Asm(address)
    saved = (30, 31)
    prologue(a, 0x20, saved)
    a.call(egw.CAVE_INIT)
    for k in range(len(ROBOT_POS)):
        a.word(i_lis(3, ha(spare.GW_SYSTEM)))
        a.word(i_addi(3, 3, lo(spare.GW_SYSTEM)))
        a.word(i_mem(LBZ, 0, 3, 0x10))
        a.word(i_rlwinm(0, 0, 0, 25, 25) | 1)  # night bit 0x40
        a.word(i_li(3, DIR_DAY))
        a.branch("beq", f"day{k}")
        a.word(i_li(3, DIR_NIGHT))
        a.label(f"day{k}")
        a.word(i_slwi(3, 3, 16))
        a.word(i_ori(3, 3, CARD_FILE))
        a.word(i_li(4, 0))
        a.word(i_li(5, 0))
        a.call(spare.FN_OBJ_CREATE)
        a.word(i_extsh(31, 3))
        a.word(i_mr(3, 31))
        a.word(i_li(4, 3))
        a.call(spare.FN_OBJ_LAYER)
        a.word(i_mr(3, 31))
        a.word(i_lis(4, ha(position(k))))
        a.word(i_addi(4, 4, lo(position(k))))
        a.call(spare.FN_OBJ_POS)
    epilogue(a, 0x20, saved)
    return spare.fits(a.assemble(), CAVE_EVENT - CAVE_INIT, "init")


def position(k):
    return CAVE_DATA + (spare.D_POS if k == 0 else 0x20)


def build_data():
    return spare.build_data(ROBOT_POS[0], pool=ORB_POOL) + struct.pack(">3f", *ROBOT_POS[1]).ljust(0x20, b"\0")


def pieces():
    return {
        CAVE_SHOW: spare.build_show(CAVE_SHOW, msg_base=egw.MSG_BASE, limit=CAVE_ASK - CAVE_SHOW),
        CAVE_ASK: spare.build_ask(CAVE_ASK, msg_base=egw.MSG_BASE, limit=CAVE_PASS - CAVE_ASK),
        CAVE_PASS: build_pass(CAVE_PASS),
        CAVE_INIT: build_init(CAVE_INIT),
        CAVE_EVENT: spare.build_event(CAVE_EVENT, CAVE_SHOW, CAVE_ASK, data=CAVE_DATA, msgs=MSGS,
                                      limit=CAVE_DATA - CAVE_EVENT, pool=ORB_POOL),
        CAVE_DATA: build_data(),
    }


def patch_dol():
    dol = bytearray(DOL.read_bytes())
    if struct.unpack_from(">I", dol, 0x48 + 4 * morph.SECTION)[0] != morph.CODE_BASE:
        raise SystemExit("Run apply_egadd_morpher_patch.py first: its DOL section 17 holds this code")
    start = dol_offset(dol, CAVE_SHOW)
    region = bytes(dol[start:start + USED_END - CAVE_SHOW])
    if any(region) and not rel_hooked(rel_data()):
        raise SystemExit(f"{CAVE_SHOW:#x}-{USED_END:#x} is not free (and this script has not run before)")
    for address, code in pieces().items():
        at = dol_offset(dol, address)
        dol[at:at + len(code)] = code
    DOL.write_bytes(dol)
    print(f"Robot code at {CAVE_SHOW:#x}-{USED_END:#x} (event {len(pieces()[CAVE_EVENT]):#x} bytes)")


# ---- REL --------------------------------------------------------------------

def rel_data():
    path = REL_DIR / REL_NAME
    if not path.exists():
        raise SystemExit("Run the earlier E. Gadd scripts first (they write the chained w02Dll.rel)")
    return bytearray(path.read_bytes())


def site_targets(data, site):
    block = import_blocks(data)[0]
    return [addend for _, section, cursor, kind, _, addend in walk_relocs(data, block)
            if section == 1 and cursor == site and kind == 10]  # R_PPC_REL24


def rel_hooked(data):
    return site_targets(data, egw.SITE_PASS) == [CAVE_PASS]


def patch_rel():
    data = rel_data()
    changed = False
    for site, old, new in ((egw.SITE_PASS, egw.CAVE_PASS, CAVE_PASS), (egw.SITE_INIT, egw.CAVE_INIT, CAVE_INIT)):
        check_words(data, site, "48000001")
        targets = site_targets(data, site)
        if len(targets) != 1:
            raise RuntimeError(f".text {site:#x} has {len(targets)} relocations: {[hex(t) for t in targets]}")
        changed |= retarget_call(data, site, old, new)
    if changed:
        (REL_DIR / REL_NAME).write_bytes(data)
        print(f"Pass and init hooks now go through the robots' caves ({REL_NAME})")
    else:
        print("Pass and init hooks already go through the robots' caves")


# ---- board data -------------------------------------------------------------

def patch_spaces(blob):
    """Append the NODES and re-link their 'from' spaces; returns the new blob, or None if already done."""
    records = spare.space_records(blob)
    count = len(records)
    if count == VANILLA_SPACES + len(NODES):
        for new, src, dst, _ in NODES:
            at, _ = records[new - 1]
            flags, kind, links = struct.unpack_from(">IHH", blob, at + 38)
            target = struct.unpack_from(">H", blob, at + 46)[0] + 1
            link = struct.unpack_from(">H", blob, records[src - 1][0] + 46)[0] + 1
            if (flags, kind, links, target, link) != (NODE_FLAG, 0, 1, dst, new):
                raise RuntimeError(f"space {new} exists but is not a robot node")
        return None
    if count != VANILLA_SPACES:
        raise RuntimeError(f"{count} spaces, expected {VANILLA_SPACES}")
    out = bytearray(blob)
    for new, src, dst, pos in NODES:
        at, length = records[src - 1]
        link = struct.unpack_from(">H", blob, at + 46)[0] + 1
        if length != 48 or link != dst:
            raise RuntimeError(f"space {src} does not link only to {dst}")
        struct.pack_into(">H", out, at + 46, new - 1)  # links are 0-based
        rot_scale = blob[at + 12:at + 36]
        out += struct.pack(">3f", *pos) + rot_scale + struct.pack(">HIHHH", 0, NODE_FLAG, 0, 1, dst - 1)
    struct.pack_into(">I", out, 0, VANILLA_SPACES + len(NODES))
    return bytes(out)


def patch_board(board, model):
    path = GAME_DATA / f"{board}.bin"
    data, offsets = mpdata.read_archive(path)
    if len(offsets) not in (CARD_FILE, CARD_FILE + 1):
        raise SystemExit(f"{board}: {len(offsets)} files, expected {CARD_FILE}")
    blob, start, end = load_spaces(data, offsets)
    spaces = patch_spaces(bytes(blob))
    current = mpdata.read_file(data, offsets, CARD_FILE) if len(offsets) > CARD_FILE else None
    if spaces is None and current == model:
        print(f"{board}: robot nodes and card (file {CARD_FILE}) already in place")
        return
    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = BACKUPS / f"{board}.bin.bak_before_egadd_robots"
    if not backup.exists():
        shutil.copy2(path, backup)
    if spaces is not None:
        data, offsets = replace_file0(data, offsets, start, end, spaces)
    if current != model:
        while len(offsets) > CARD_FILE:
            data, offsets = wheel.drop_last_file(data, offsets)
        data, offsets = mpdata.append_files(data, offsets, [model])
    path.write_bytes(data)
    print(f"{board}: nodes {[n[0] for n in NODES]} (flag {NODE_FLAG:#x}); robot card is file {CARD_FILE}")


# ---- text -------------------------------------------------------------------

def bank_count(data):
    """Records in bank 0x30 of a messdata file."""
    _, start, _ = _bounds(data, BANK)
    return struct.unpack_from(">I", data, start)[0]


def patch_messages():
    for name in MESS_NAMES:
        current = MESS_OUTPUT_DIR / name
        if not current.exists():
            raise SystemExit(f"Run apply_egadd_wheel_patch.py first ({current} is missing)")
        edited = edit_bank(current.read_bytes(), {}, name, bank=BANK, bank_records=BANK_RECORDS, append=RECORDS,
                           known_tails=())
        current.write_bytes(edited)
    print(f"Robot lines: bank {BANK:#x} records {MSGS[0]}-{MSGS[-1]}")


def main():
    patch_dol()
    patch_rel()
    model = card_model()
    for board in BOARDS:
        patch_board(board, model)
    patch_messages()


if __name__ == "__main__":
    main()
