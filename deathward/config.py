# DEATHWARD -- a turn-based roguelike where failure is the only progression.
# Copyright (C) 2026 Dale Cook
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <https://www.gnu.org/licenses/>.

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

# --- Magical-armour drop bands (Plan C) -------------------------------------
# At most ONE magical-armour piece per floor. T5 is rolled first (its own,
# deep-weighted band); only if it misses is T4 rolled. Each entry is
# (lo_floor, hi_floor, present_chance). Floors 8-9 give T4 a higher chance
# because T5 does not start until floor 10 (no early dead zone).
ARMOUR_MAGICAL_T4_BANDS = [(8, 9, 0.20), (10, 11, 0.12), (12, 15, 0.10), (16, 20, 0.06)]
ARMOUR_MAGICAL_T5_BANDS = [(10, 13, 0.08), (14, 17, 0.12), (18, 20, 0.20)]

FOV_RADIUS = 8
MONSTER_SIGHT = 9         # how close (in tiles, within FOV) a monster notices the player

SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deathward_save.json")

# _autosave() updates the in-memory run every turn regardless, but only actually
# persists (disk write, or a localStorage write in the browser build) once every
# this-many turns. Written every turn was fine on disk but too hot for localStorage
# (~8 turns/sec) with no suspend-on-close to fall back on in a browser tab.
AUTOSAVE_INTERVAL_TURNS = 5

# Bump this whenever the DUNGEON GENERATOR changes shape. A save from an older
# generator still holds a map you drew and traps you found -- but of a dungeon whose
# walls are now somewhere else. Rather than let the player walk around with a
# remembered map that quietly lies to them, we re-cut the stone and forget the map.
# The Kodex, the deaths and the telemetry all survive: those are about YOU, not the
# place.
LAYOUT_VERSION = 4

# Bumped when the run-save (suspend/resume) serialization shape changes. A save
# whose run block carries a different version is discarded -- Continue falls back
# to a fresh run -- exactly as LAYOUT_VERSION discards a stale map. Bumped for
# Syrinx's new Monster fields (hidden/hidden_turns/pillar_x/pillar_y/retreating).
RUN_SAVE_VERSION = 4     # 4: floor 8's gate state (mouth_sealed/stairs_locked/boss_spawned)

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

# THE HAMMER'S STAGGER. A hammer does not gamble its stun on a die roll -- it lands on
# a rhythm you can play around: it staggers the FIRST blow against a given enemy, then
# every Nth blow after. Deterministic, so the control is legible (and it costs no rng
# draw). These are the dials: crank the cadence tighter or the hold longer if the
# hammer still feels weak, but a 2-turn hold on a tight cadence perma-locks a duel.
HAMMER_STUN_CADENCE = 3          # stun on hits 1, 1+N, 1+2N, ... against each enemy
HAMMER_STUN_TURNS   = 1          # turns the stagger holds

FREEZE_CHANCE       = 0.25        # Winter's Edge / Glacial Flail: chance to freeze on hit
FREEZE_TURNS        = 1           # a freeze is one player turn of the stun system

SLIPSTEP_HIT_CADENCE = 4          # every Nth damaging hit taken triggers the escape
SLIPSTEP_BLINK_DIST  = 2          # chebyshev tiles the escape leaps
PHANTOM_DODGE_CHANCE = 0.25       # Phantom Boots: chance to sidestep an incoming blow
FEAR_CHANCE         = 0.25        # Reaper's Whisper: chance to rout on hit
FEAR_TURNS          = 6           # turns a frightened thing flees

POISON_TURNS        = 3           # Basilisk Maul: turns the venom keeps eating
POISON_DMG          = 2           # damage per poisoned turn

# --- magical armour (Phase 1) ---
ARMOUR_RETAL_RECHARGE = 3      # retaliation trio: turns between on-struck triggers
ARMOUR_CAPSTONE_RECHARGE = 4   # Blinding Light / Robe of Hades
CINDER_BURN_TURNS = 2          # Cinderplate: attacker burns this many turns
VENOM_POISON_TURNS = 3         # Venomweave: attacker poisoned this many turns
BASTION_CAP = 8                # Bastion: no single hit exceeds this
LIFEWEAVE_HEAL = 2             # Lifeweaver: hp knitted per turn while worn
BLINDING_RADIUS = 2            # Blinding Light: stun radius (tiles)
BLINDING_STUN_TURNS = 2        # Blinding Light: stun duration
LASTBREATH_SANCTUARY = 1       # Last Breath: turns untouchable after the save

# --- magical armour (Phase 2) ---
FADE_INVIS_TURNS = 2       # Fadecloak: turns of vanish on the 4th hit
FADE_HIT_CADENCE = 4       # Fadecloak: every Nth hit taken triggers it
SHADE_SUBMERGE_MAX = 10    # Shademail: max turns you may stay in stone
SHADE_CRUSH_DMG = 2        # Shademail: damage/turn when submerged with no exit
SHADE_REENTER_CD = 5       # Shademail: turns before you may dive again

ENRAGE_CHANCE       = 0.20        # Betrayer's Edge: chance to send the struck thing berserk
ENRAGE_TURNS        = 6           # turns it attacks whatever is nearest

VOID_KILL_CHANCE    = 0.10        # Scimitar of the Void: chance to unmake outright

FULGURITE_INCORP_MULT = 1.5       # Fulgurite's bonus vs wraith/poltergeist

# --- Syrinx (floor 8 mini-boss) -------------------------------------------
SYRINX_HIDDEN_MAX = 5      # turns she may stay hidden before a forced emergence
SYRINX_DEPTH      = 8      # the floor her arena is on
SYRINX_STUN_TURNS = 1      # turns fully vulnerable after her blow lands
SYRINX_PUSH_DIST  = 5      # tiles the gust shoves the player back. long enough that
                           # the slide crosses real floor -- and her arena's floor is
                           # trapped, which is where her damage actually comes from.
SYRINX_FIRE_MULT  = 2.0    # matches the stone golem's existing fire weakness
SYRINX_BLOW_RANGE = 3      # tiles the gust can be thrown from. she used to hunt out to
                           # RANGE=9 and poke from range; now the poke IS the close
                           # fight -- she is not a predator that runs you down, she is
                           # stone punishing anyone who reaches her. this replaced the
                           # old hard-coded RANGE=9 everywhere it appeared in her AI.
SYRINX_STANDOFF   = 6      # beyond this she closes the gap; within it she manoeuvres
                           # instead -- the real leash on her now that the sealed-floor
                           # arena leash means nothing (the arena IS the floor). she
                           # will line herself up on your row or column, but she will
                           # not walk into your reach to do it.

# --- floor 8: her hall ----------------------------------------------------
# The geometry is FIXED -- cut identically in every game -- and only the hazards are
# re-dealt per game. 31x23 is ~2.7x the largest room the generator can make (a 20x13
# hall), because every part of this fight needs open floor: pillars are walls, and the
# shove stops at the first one, so a dense lattice would cut every push short and the
# trapped floor would never get crossed.
ARENA_W, ARENA_H          = 31, 23
ARENA_PILLAR_PITCH        = 6      # one column every 6th tile, both axes
ARENA_PILLAR_COLS         = 5
ARENA_PILLAR_ROWS         = 4      # 5 x 4 = twenty single-tile columns
ARENA_MARGIN_X            = 3      # floor between the outer columns and the walls
ARENA_MARGIN_Y            = 2
ANTE_W, ANTE_H            = 9, 7   # the prep room. a vendor stands here one day.

# ~150 hazards across ~680 eligible floor tiles (~22%), so a five-tile shove usually
# crosses one and often two. (An earlier pass at 50/~7% left her blow, not the room,
# as the real threat -- a five-tile shove crossed a hazard barely a third of the
# time.) The minefield DEPLETES as the fight runs on: dart, gas and glyph are
# one-shot once sprung. The spike pit is not -- it re-fires forever and costs you a
# turn climbing out, which is a turn she is winding up in.
ARENA_TRAPS = 150

# --- held-key movement ---------------------------------------------------
# A tap is exactly one step. Hold the key past the delay and the hero keeps
# walking. The delay has to be long enough that careful single steps (the whole
# point of a turn-based game) never turn into an accidental charge into a brute.
#
# The interval is a LEGIBILITY number, not a safety one -- safety is walk_step's job,
# which halts the walk for loot underfoot or a monster arriving in view. This is only
# about the walk being readable as movement instead of a blur: 0.085 was ~12 steps a
# second, faster than the eye tracks. Tune it by feel; nothing is pinned to it.
MOVE_REPEAT_DELAY    = 0.22      # seconds held before auto-walking begins
MOVE_REPEAT_INTERVAL = 0.13      # seconds between steps while held (~7.7 a second)
