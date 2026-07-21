# Boots Rebalance — Ordinary Boots Distribution (Generation-Placed, Found-Only)

**Date:** 2026-07-21
**Status:** design, pending review
**Scope:** a follow-up to the boots Plan 1 (ordinary tier + magical relocation), built on the
same `boots-rebalance-ordinary-tier` branch. It changes only *how ordinary boots are
distributed* — making them scarce, found-only, one-per-floor generation-placed finds that
taper out by the deep floors, exactly like ordinary weapons. It does not change boot stats,
tiers, sprites, or the magical boots.

## Problem

After Plan 1, ordinary boots (Leather T1, Mail T2, Plate T3) still come from the generic
`gear_pool`, which feeds the multi-source loot pipeline (floor drops + chests of 1–3 +
monster bodies) *and* the vendor *and* the floor-1 gift. Three consequences the design
should not have:

1. **Boots appear on floor 1** (Leather is gated at depth ≥ 1, and the floor-1 gift can hand
   you a boot).
2. **A floor can yield multiple ordinary boots** — because the generic loot pool is rolled
   many times per floor.
3. **Ordinary boots never stop dropping** — no upper cutoff, so they keep appearing on the
   deep floors that should be magical territory.

## Goals

- Ordinary boots become **found-only** — never sold by the vendor, never gifted. (The user
  chose full weapon-parity here; what the vendor sells instead is a separate future task.)
- **One ordinary boot per floor, at most** — never multiples. This means generation-placed,
  like weapons, and removed from the generic loot pool.
- **No ordinary boots on floor 1**, and **none past floor 15** — the deep floors are magical
  territory, mirroring how ordinary weapons taper out.
- Preserve determinism: boot generation draws only from `(rng, depth)`, never the Kodex, so a
  blind and an omniscient run of the same seed stay bit-identical.

## Non-goals

- No change to boot stats, tiers, names, sprites, or the auto-swap tradeoff rule (all Plan 1).
- No change to the **magical** boots' distribution — they stay in `gear_pool` (generic loot on
  floors 8+) until the magical rework (Plan 2). "One per floor" applies to *ordinary* boots.
- No rework of what the vendor stocks now that boots leave it — deferred (the vendor will sell
  armour + magical-boot-free ordinary gear; revisiting its inventory is a future task).

## Design

### 1. Ordinary boots leave `gear_pool`

`gear_pool(depth)` today iterates `(ARMOURS, BOOTS)` and appends by tier. It is rewritten so
that:

- **Armour** keeps its tier 1/2/3 depth gates (unchanged) — armour distribution is untouched.
- **Boots**: only **magical** boots (tier ≥ 4) are appended, and only at `depth >= 8`
  (unchanged from Plan 1). **Ordinary boots (tier 1–3) are no longer added at all.**

Because `gear_pool` is the single source for the vendor, the floor-1 gift, and the generic
`roll_loot`/chest/body loot, this one change removes ordinary boots from **all three** at once:

- **Vendor:** its `tier <= 3` filter (Plan 1) now yields armour only — ordinary boots are gone
  from the pool, magical boots are still excluded by the filter. (Filter stays; still needed.)
- **Floor-1 gift:** it draws `gear_pool(1)`, now tier-1 **armour only** — so no boot can be
  gifted, satisfying "no boots on floor 1."
- **Generic loot:** floor drops, chests, and monster bodies can no longer contain an ordinary
  boot, so a floor cannot accumulate several.

### 2. `roll_floor_boots(rng, depth)` — the one-per-floor placement

A new function mirroring `roll_floor_weapons`, returning **at most one** ordinary boot key
(a list of 0 or 1 keys). It is deterministic on `(rng, depth)` and reads nothing else.

**Floor bands** (lower unlocks carried from Plan 1; upper cutoffs new):

| Boot | Present on floors |
|---|---|
| `boots_leather` | 2 – 10 |
| `boots_mail` | 3 – 15 |
| `boots_plate` | 5 – 15 |

Resulting availability: floor 1 none; floor 2 leather; 3–4 leather/mail; 5–10 all three;
11–15 mail/plate; 16–20 none.

**Present-chance:** on any floor with at least one valid boot (floors 2–15), a boot is placed
with **50% probability**; otherwise the floor holds none. (Floors 1 and 16–20 always none.)

**Selection:** when several boots are valid at the depth, choose **uniformly at random** among
them. Ordinary boots are a speed↔defense tradeoff, not a power ladder, so the player finds one
of the currently-available options and decides whether its tradeoff suits them — no depth-based
skew.

### 3. Placement at floor generation

In `dungeon.py`'s level generation, immediately after the weapons-placement loop, a boots loop
places each key `roll_floor_boots` returns as a `Drop(..., "gear", bkey)` on a free tile
(`_free_tile(avoid_start=True)`), the same way deep-floor weapons are placed. Boots carry no
enhancement/bonus (only weapons do), so the drop uses the default `bonus=0`. The call sits at a
fixed point in the generation order so the RNG stream stays reproducible and Kodex-independent.

## Surfaces touched

- **`items.py`** — rewrite `gear_pool` to drop ordinary boots (keep armour gates + magical-boot
  gate); add `roll_floor_boots(rng, depth)` and its floor-band table.
- **`dungeon.py`** — add the boots-placement loop after the weapons loop; update the stale
  "Armour/boots only" comment on the floor-1 gift to "Armour only."
- **`tests.py`** — rewrite the Plan 1 test `test_gear_pool_keeps_magical_boots_out_of_the_shallows`
  so it asserts ordinary boots are *no longer* in `gear_pool` at any depth (magical-boot gating
  assertions stay); add tests for `roll_floor_boots` (floor-1 empty, band edges, ≤1 per floor,
  nothing past 15, uniform selection reaches every valid boot, ~50% present-rate, determinism).

## Testing considerations

- **Determinism / bit-identical:** `roll_floor_boots` must draw from `(rng, depth)` only. The
  existing blind-vs-omniscient invariant test (`TestKnowledgeIsNotPower`, tests.py:323) must stay
  green — placing boots reads no Kodex state.
- **One-per-floor:** assert `len(roll_floor_boots(rng, depth)) <= 1` across seeds and depths.
- **Bands:** floor 1 and floors 16–20 always return `[]`; leather never appears past 10; mail/
  plate never past 15; each boot appears within its band.
- **Found-only:** `gear_pool(depth)` contains no ordinary boot at any depth; the vendor and the
  floor-1 gift therefore cannot surface one (the gift falls back to armour on floor 1).

## Open tunables (safe to settle in playtest)

- The 50% present-chance.
- The exact band cutoffs (leather ≤ 10; mail/plate ≤ 15).
- Uniform vs. a mild depth-skew in boot selection.
