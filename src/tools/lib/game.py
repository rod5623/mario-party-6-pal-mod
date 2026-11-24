"""Game addresses (GP6P01) shared by several patches.

Patch-specific addresses stay in their scripts. FN_PROMPT here is fn_8016B718 (message window with
choices); apply_star_shuffle_bet_patch.py uses a different prompt, 0x8016B7A4, under the same local name.
"""

FN_PRACTICE_CHECK = 0x8006A7B0  # fn_8006A7B0(flag)

GW_SYSTEM = 0x80283290

GW_PLAYER = 0x80282E70

PLAYER_SIZE = 0x108

FN_MESSAGE = 0x8016B36C

FN_WAIT_MESSAGE = 0x8016C7D8

FN_RANDOM = 0x8014CD78

FN_STARS = 0x8015CE98

FN_ADD_STARS = 0x8015CF64

FN_ORB_MAX = 0x8015D6B8

FN_ORB_COUNT = 0x8015DFF0

FN_ORB_ADD = 0x8015D6FC

FN_PLAYER_HOLD = 0x801565EC  # fn_801565EC(player, 0), as Star Shuffle calls before it talks

FN_PLAYER_MOTION = 0x8015BFB4  # fn_8015BFB4(player, motion, f1, f2, flags)

FN_PROMPT = 0x8016B718       # fn_8016B718(2, message, speaker, 0): message window with choices

FN_CHOICE = 0x8016C52C       # 0 = Yes, 1 = No, -1 = cancelled

FN_COINS = 0x8015C770

FN_ADD_COINS = 0x8017E03C  # (player, amount, 1, 1)
