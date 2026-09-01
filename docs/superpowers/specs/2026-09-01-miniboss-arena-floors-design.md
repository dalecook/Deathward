# Mini-boss arena floors — design

**Date:** 2026-09-01
**Status:** design agreed, not yet planned
**Supersedes:** the floor-8 arena described in `2026-08-31-syrinx-floor8-miniboss-design.md`
(a reserved-room arena on an otherwise ordinary floor). Her state machine, stats,
telegraphs, immunities and drops from that spec are unchanged and carry over.

## Why

Syrinx shipped as a monster standing in the biggest room of an ordinary floor. Two
problems came out of playtest and review:

1. **She is optional.** Her arena is the biggest non-gate room, chosen with no
   reference to where the stairs landed. You can often walk past her to the way down.
   "Mini-boss" should mean something about passage, not about room size.
2. **She is easy.** Her signature move shoves you two tiles and does 1-3 damage. The
   shove costs the player nothing at all — `_syrinx_knockback` moves the player
   without calling `_enter_tile()`, so it drags you over traps without springing any
   of them. Her whole design is "minimal chip damage, you get worn down if you are
   inefficient", and the thing meant to wear you down was inert.

The fix for both is the same: floor 8 stops being a dungeon floor and becomes her
arena, sealed at both ends, with a trapped floor that her shove throws you across.

## The mini-boss contract

Written as prose deliberately. Floor 15's boss does not exist yet, and the shape of an
arena follows from the boss's mechanics — an abstraction written now would be guessing.
The behaviours below are what generalise; the room is not.

> A mini-boss floor is **entered** by a gate that seals behind you, **prepared for** in
> an antechamber, **committed to** through a one-way mouth, and **left** only by a way
> down that opens when the boss dies.

Three gates, one object, each opening in one direction only. Floor 15 (early thinking:
a stealth assassin in a large dark maze, reduced visibility) is expected to use the same
three gates and supply its own cutter and its own FOV radius.

## Floor 8: the floor

Floor 8 is cut by a bespoke cutter, not `_cut_stone`. No room generator, no corridors,
no ambient population, no chests. Geometry is **fixed and identical in every game**;
only the hazards are re-dealt per game.

### Geometry

| | |
|---|---|
| Arena | **31 × 23** = 713 tiles (~2.7× the largest hall the generator can make, 20×13 = 260) |
| Pillars | **20**, single-tile, a 5 × 4 grid on a **6-tile pitch** |
| Pillar margins | 3 tiles to the left/right walls, 2 to the top/bottom |
| Antechamber | small prep room, joined to the arena by a one-tile mouth |
| Fits | the map is 64 × 40, so arena + antechamber sit comfortably |

Twenty columns in a room that size is a cathedral with something circling in it, not a
thicket. That is deliberate: every element of this fight needs **open floor** to work.
Pillars are walls, and `_syrinx_knockback` stops at the first non-walkable tile, so a
dense lattice would cut every shove short at two tiles and the hazards would never get
crossed. Sparse cover also means she must *commit* to reach a hiding place, and is
exposed while she travels.

The viewport is 36 × 18 tiles with a camera that scrolls, so the arena is wider than
tall but taller than the screen. `FOV_RADIUS = 8` is unchanged: you light 8 tiles, less
once columns eat your sightlines.

### The three gates

1. **Arrival.** You descend from 7 and the way up seals behind you. This is floor 1's
   existing rule with a second condition — `ascend()` already returns `"sealed"` at
   depth 1 ("the gate you came in by. it is not a door now.").
2. **The mouth.** The antechamber is yours for as long as you want it: read your pack,
   drink what you are going to drink. Step through and it shuts.
3. **The way down.** Visible from the moment you enter the arena, and shut. It opens
   when she dies. Precedent is the Warden's `descend()` refusal ("There is no way down.
   There is only the Warden.").

A shut gate is a `WALL` tile for movement, line-of-sight and pathfinding. The level
remembers gate coordinates and the renderer draws a **portcullis** there. No new tile
semantics — but a sealed doorway drawn as plain wall reads as a bug, so it must be
visibly a gate.

### Arrival sequence

All within the turn you cross the mouth:

1. The mouth gate falls.
2. The arena's **stone** is revealed entire — the whole columned hall. Scale is the
   point, and the room should land as vast the moment it closes.
3. She materialises at the far end, holds one turn, and sinks into a pillar —
   **unwitnessed**, ~25 tiles beyond your FOV.

The reveal touches `explored` and never `seen`. The codebase already draws exactly this
line: `explored` is the stone you have seen (a Scroll of Mapping fills it in), `seen` is
contents you have laid eyes on this run, and "nothing but your own line of sight ever
sets this — no scroll does". She is contents. **Nothing ever reveals her.**

Traps are stone but *undiscovered*, and an undiscovered trap renders as clean floor. So
the reveal defuses nothing: you are looking at a hall whose shape you can see and still
cannot safely cross.

### No escape; the scrolls change jobs

Scroll of Escape (UUL, random room) and Scroll of Teleport (ZEPH, aimed) work normally
**inside** the arena. The antechamber leaves the destination pool the moment the mouth
shuts: UUL never rolls it, ZEPH's cursor refuses it.

This is not a nerf. She never melees, shoves you away from her, and is fully vulnerable
for exactly one turn after her blow lands — so the fight is a distance war she wins by
default, and an aimed teleport is the gap-closer that converts her stun into damage. On
floor 8 those scrolls stop being an exit and become the best offensive item you can
carry.

Rationale for barring the antechamber: the floor has only two exits (up, sealed on
arrival; down, locked until she dies, and inside the arena). Teleporting into a sealed
antechamber would leave no legal move — a softlock, against the completability guarantee
the suite enforces. The alternative, a one-way-passable mouth, would restore
retreat-and-heal and introduce tile semantics that exist nowhere else in the game.

### The hazards do the killing

`BASE_HP = 26` and this game has no levelling, so you meet her with roughly 26 HP. Her
own blow is **1-3**. She is not the damage; the room is.

**Roster: dart, spike pit, gas vent, fire glyph. No alarm rune** — `wake_all()` in a
one-monster sealed room wakes a boss who is already hunting you.

**Starting density: ~50 traps** across 693 floor tiles (~7%), so a five-tile shove
crosses a hazard roughly a third of the time and occasionally two. Dealt from `lrng`, so
they are identical on every re-entry within a game and re-dealt in a new one: dying on
floor 8 buys you knowledge of *this dungeon's* arena.

The minefield **depletes**. Dart, gas and glyph are one-shot (`_enter_tile` skips them
once sprung). The **spike pit re-fires forever** and costs a turn climbing out
(`player.stuck = 1`) — so the room grows safer as the fight runs on, except for the pits,
which stay, and hold you still while she winds up.

### Balance changes

- `SYRINX_PUSH_DIST` **2 → 5**.
- The shove **springs everything it drags you across**, at full effect. Existing
  instantaneous traps only — no persistent burning tiles, no hazard fields. Because
  these traps resolve immediately, everything that fires is fully resolved by the time
  you come to rest; there is no pending-effect window to manage.

## Implementation notes

### `dungeon.py`
- Floor 8 branches away from `_cut_stone` into a bespoke cutter. It must still populate
  `self.rooms` (antechamber and arena as real `Room` objects — UUL indexes
  `level.rooms`), `entrance`, `start`, `gate_room`, `stairs`, and the pillar lattice.
- `_populate` does not run on floor 8. No ambient monsters, no chests.
- `_install_traps` takes a floor-8 branch: its own count and four-trap roster, placed
  only on arena floor, never on a pillar, the mouth, the stairs, or her arrival tile.
- `syrinx_pillars()` returns the 20-pillar lattice instead of six scattered spots.
- `_populate_syrinx` no longer places her at generation; she spawns on commit.
- `_restore` already re-carves her pillars on resume; that path now covers the lattice.
- **Corpse placement needs no change.** `_place_corpse` puts your body on the exact tile
  you fell on, and floor 8's stone is fixed, so the tile is still there and still
  walkable next run. Die to her and your gold lies in her arena: getting it back means
  crossing the mouth and fighting her again. Its existing eviction fallback covers the
  one odd case (a grave that is no longer walkable). One consequence worth stating: if
  you die in the *antechamber* — arriving poisoned from floor 7 is the only real way —
  that corpse is recoverable only before you commit, because nothing crosses back.

### Level state and saves
Three new booleans — mouth shut, stairs locked, she has spawned — into `to_dict` and
`_restore`, plus the gate coordinates for rendering. **Bump `RUN_SAVE_VERSION`.**
Suspend in the antechamber and she must not exist on resume; suspend mid-fight and she
must, exactly where she was.

### `world.py`
- `ascend()` gains the boss-floor condition beside its depth-1 case.
- `descend()` refuses while the stairs are locked, in the Warden's voice.
- Crossing the mouth fires the arrival sequence above, in one turn.
- Her death unlocks the way down, with a log line and an effect on the stairs.
- `_syrinx_knockback`: distance from config; `_enter_tile()` on each tile crossed; stop
  the slide if the player dies partway.
- UUL drops the sealed antechamber from its room pool; ZEPH's targeting refuses it.

### `monsters.py`
One new beat at the top of her state machine — materialise visible, hold one turn, then
retreat and hide — ahead of the existing hidden/telegraph/emerge/blow/stun/retreat loop,
which is otherwise untouched. Her room leash still works: the arena is a `Room`, so
`Room.contains()` holds.

### `render.py`
Portcullis drawn on the remembered gate coordinates.

## Testing

- **Completability**: the way down is reachable once she is dead, and no reachable state
  leaves the player without a legal move.
- Both gates seal (on arrival, on commit); `ascend` refused; `descend` refused until she
  dies, permitted after.
- The shove springs every trap in its path, and halts on player death.
- Neither scroll ever lands the player in the sealed antechamber.
- Spawn/seal/lock flags survive a suspend/resume round trip.
- The pillar lattice never blocks the mouth, the stairs, or her arrival tile.
- The arrival reveal sets `explored` and leaves `seen` untouched.

## Out of scope

- **The antechamber vendor.** Wanted, deferred. The design leaves room for it; it is not
  built here. (Related: the deferred "vendors sell magical items at high prices" rework.)
- **Floor 15.** Contract only, no machinery.
- Persistent burning tiles / hazard fields.
- Any one-way-passable tile.

## Dials to tune by playing

`SYRINX_PUSH_DIST` (5), arena trap count (~50), pillar pitch (6), arena dimensions
(31 × 23). Three difficulty increases land together here — a longer shove, a trapped
floor, and her pillar count going from 6 to 20, which makes re-hiding much easier.
Expect to move these in playtest rather than argue them in advance.
