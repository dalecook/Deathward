"""Constants, palette and tuning for DEATHWARD."""

import os

TILE = 32                        # bigger tiles: the sprites need room to read
VIEW_W, VIEW_H = 36, 18          # tiles visible
W = TILE * VIEW_W                # 1152
LOG_H = 34                       # the one-line log strip, just below the map
HUD_H = 132
H = TILE * VIEW_H + LOG_H + HUD_H  # 576 + 34 + 132 = 742
FPS = 60

MAP_W, MAP_H = 64, 40
DEPTH_MAX = 20
FOV_RADIUS = 8

SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deathward_save.json")

# Bump this whenever the DUNGEON GENERATOR changes shape. A save from an older
# generator still holds a map you drew and traps you found -- but of a dungeon whose
# walls are now somewhere else. Rather than let the player walk around with a
# remembered map that quietly lies to them, we re-cut the stone and forget the map.
# The Kodex, the deaths and the telemetry all survive: those are about YOU, not the
# place.
LAYOUT_VERSION = 4

# --- palette -------------------------------------------------------------
BG          = (10, 11, 16)
FLOOR       = (34, 38, 50)
FLOOR_LIT   = (52, 58, 76)
WALL        = (58, 64, 84)
WALL_LIT    = (86, 95, 120)
SEEN        = (22, 25, 34)       # explored but not currently visible
SEEN_WALL   = (36, 40, 54)

INK         = (228, 234, 244)
DIM         = (128, 140, 164)
FAINT       = (70, 78, 98)
GOLD        = (240, 198, 90)
BLOOD       = (206, 66, 74)
HEAL        = (110, 220, 130)
MANA        = (110, 170, 240)
UNKNOWN     = (24, 26, 34)
UNKNOWN_EDGE= (64, 70, 92)

PLAYER      = (120, 226, 220)
CORPSE      = (168, 128, 200)
STAIRS      = (250, 226, 140)
ENTRANCE    = (140, 190, 240)
CHEST       = (198, 152, 88)
TRAP        = (232, 96, 120)
ITEM        = (150, 200, 255)

# --- player base ---------------------------------------------------------
# THE PACK: six slots, and a slot holds up to three of ONE thing.
#
#   - picking something up tops up the lowest slot of that type that has room
#   - if every stack of that type is full, it opens the lowest EMPTY slot
#   - if there is no empty slot, the pickup is refused and the item stays where it lies
#   - consuming from a slot pulls items DOWN out of later slots of the same type to
#     refill it -- only as many as it needs, and only ever downward
#
# So the ceiling is 18 items, but only if they are the same few things. Six different
# potions is six items. Slot numbers are stable, which is what makes 1-6 muscle memory.
PACK_SLOTS   = 6
STACK_MAX    = 3

# --- the vendor ----------------------------------------------------------
# Something is down here that will trade with you. It only ever walks the deep
# floors -- there is no point selling to a man with no gold.
#
#   floors above VENDOR_MIN_DEPTH  : 0%, always
#   the bottom floor (DEPTH_MAX)   : 0%. it does not stand in the Warden's room.
#   arriving at VENDOR_MIN_DEPTH   : 5%
#   each floor deeper              : +5%
#   each floor back up             : -5%   (so stair-bouncing nets you nothing)
#   descending away from a vendor  : reset to 5%
#
# A floor rolls ONCE, on your first arrival. Without that, bouncing between two
# floors would give you unlimited re-rolls at the same odds, and the +/-5% would be
# stopping the wrong exploit.
VENDOR_MIN_DEPTH = 5
VENDOR_BASE_PCT  = 5
VENDOR_STEP_PCT  = 5

VENDOR_COLOR = (214, 176, 96)

BASE_HP      = 26
BASE_SPEED   = 100               # energy gained per tick; act at 100
ACT_COST     = 100

# --- held-key movement ---------------------------------------------------
# A tap is exactly one step. Hold the key past the delay and the hero keeps
# walking. The delay has to be long enough that careful single steps (the whole
# point of a turn-based game) never turn into an accidental charge into a brute.
MOVE_REPEAT_DELAY    = 0.22      # seconds held before auto-walking begins
MOVE_REPEAT_INTERVAL = 0.085     # seconds between steps while held
