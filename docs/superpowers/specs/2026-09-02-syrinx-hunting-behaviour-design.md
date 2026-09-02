# Syrinx's hunting behaviour — design

**Date:** 2026-09-02
**Status:** design agreed, implementing directly (single cohesive change; no separate plan doc)
**Follows:** `2026-09-01-miniboss-arena-floors-design.md`, and the 2026-09-02 playtest fixes

## Why

Playtest report: *"Syrinx hunts you down across open floor, that's not right."*

Her loop is hidden → telegraph → emerge → **hunt** → blow → stunned → retreat → re-hide. The
hunt step is `_step_toward(world, p.x, p.y)`, run every turn until she has an aligned clear
line within `RANGE = 9`. So a creature whose whole identity is hiding in stone and striking
from cover spends most of the fight walking across a lit room at the player. Since she now
matches the player's speed exactly, she can also follow forever, and she is exposed the entire
time.

The leash that was supposed to prevent this:

```python
# She is a boss-ROOM fight, not a floor-wide hunter...
if not world.level._syrinx_arena().contains(p.x, p.y):
    return
```

did not break — it stopped meaning anything. It was written when her arena was one room among
many on an ordinary floor. The arena is now the whole of floor 8, so the check is always true.

## The idea

**She does not need to hunt, because the locked gate hunts for her.** The way down does not
open until she is dead, so the player must come to her. She can wait in the stone and punish
arrival.

So the blow stops being a ranged poke and becomes a close-range rebuff: **she blows when the
player is within 3 tiles and aligned**, not when she has worked her way into a line at 9. The
player spends the fight closing; she spends it throwing them back across a floor holding 150
hazards. The knockback stops being repositioning flavour and becomes the economy of the fight.

## The behaviour

Checked in order, each turn she is emerged and not retreating:

| # | Condition | She does |
|---|---|---|
| 1 | Player adjacent **and not aligned** (i.e. diagonal) | **Steps away.** |
| 2 | Player aligned, within `SYRINX_BLOW_RANGE`, line clear | **Telegraphs**, resolving next turn. |
| 3 | Player within `SYRINX_STANDOFF` | **Sidesteps toward alignment. Does not close.** |
| 4 | Player beyond `SYRINX_STANDOFF` | **Steps toward**, one tile. |

**Rule 1 closes a real blind spot.** Diagonal adjacency means neither the same row nor the same
column, so it is not "aligned" and she cannot gust from it — a player standing diagonally on top
of her could hit her indefinitely with no counter. She recoils instead, which also reads
correctly: she is not a predator, she is something defending a room from a thing that can hurt
her.

**Rule 3 is the fight.** This is her at her most characteristic — patient, lining the player up,
refusing to walk into reach. It is also the real leash: what stops her closing, rather than what
stops her chasing.

**Rule 4 stops her being a statue.** She closes only to bring the player back into the band, not
to reach them. In the user's words: she wants you out of there, and that means dead, so she will
help it along — but you are still dangerous.

## Constants

Both new, both `config.py`, both deliberately untested balance dials:

- `SYRINX_BLOW_RANGE = 3` — replaces the hard-coded `RANGE = 9` in `_ai_syrinx`.
- `SYRINX_STANDOFF = 6` — beyond this she closes; within it she manoeuvres.

## What this deletes

- **`RANGE = 9`.** Her blow now reaches 3. A large, deliberate nerf to her raw threat: the
  shove is what hurts now, and the shove only happens up close.
- **The arena leash.** Deleted outright, not repaired. The standoff band replaces it.

## Consequences we accepted

**The punish window needs earning.** She is helpless for one turn after a blow lands
(`SYRINX_STUN_TURNS`), but the blow has just thrown the player 5 tiles away, so the opening is
not free any more. Two ways to take it, both deliberate:

- **Fight with your back to a pillar or wall.** `_syrinx_knockback` stops at the first
  non-walkable tile, so a short shove leaves the player in reach. This makes the 20-column
  lattice something to position *against*, not just cover to hide behind.
- **An aimed Teleport scroll**, already established as the gap-closer on this floor.

**The telegraph is still the counterplay.** She warns a turn before the blow resolves, so
stepping out of the lane dodges it. At range 3 that is a tight decision rather than a leisurely
one.

**A pillar in the eyeline still fizzles the blow** (`world.line_clear`). Unchanged.

## Testing

- Each of the four rules fires in its own band, and in the right priority order.
- Diagonal-adjacent no longer leaves her helpless: she steps away rather than standing there.
- She does **not** close while the player is inside the standoff band — the specific regression
  this design exists to prevent.
- She does close when the player is well outside it, so camping at range does not stall.
- A blow still requires alignment, range, and a clear line; a pillar between them still fizzles.
- Her hidden/telegraph/emerge/stun/retreat/re-hide states are untouched and still pass.

## Out of scope

- Her speed floor of 100 and the Kodex-gated telegraph markers — both deferred by the user on
  2026-09-02, recorded in memory.
- Shademail crossing the sealed mouth — still an open design question.
- Any change to the hazards, the gates, or the arena geometry.
