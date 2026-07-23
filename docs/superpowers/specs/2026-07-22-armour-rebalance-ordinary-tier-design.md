# Armour Rebalance — Ordinary Tier (Plan A)

**Date:** 2026-07-22
**Status:** design, pending review
**Scope:** the first of the armour passes — the **final** leg of the gear triad, after
weapons and boots. This plan clean-slates the *ordinary* armour tier (leather/mail/plate),
moves armour to the same scarce, generation-placed, found-only model as weapons and boots,
reworks floor 1 into a single coin-flip gift, and narrows the vendor to consumables. The
magical roster (T4/T5 identities, including the graduated thorns + wraithsilk) and the deep
economy (rarity/uniqueness/persistence/collection) are deliberate follow-up specs.

## Problem

Armour is the least-developed slot of the triad. It carries seven pieces
(rags/leather/scale/chain/thorn/plate/silk) — a mix of plain rungs and trait-bearing
one-offs — with **no magical tier** at all, while weapons and boots each got a clean
ordinary ladder *plus* a full magical roster. Worse, armour is now the **only** slot still
living in `gear_pool()`: it is sold by the vendor, handed out by the floor-1 gift, and
dropped through the generic loot tables — none of which is true of weapons or boots any
more, both of which are scarce and generation-placed. Armour is out of step on structure,
scarcity, and content.

## Goals

- Clean-slate the ordinary tier into a **four-rung leather/mail/plate ladder** that reuses
  the exact material vocabulary established by ordinary boots, so a player reads "mail is
  the middle, plate is heavy and slow" identically across both slots.
- Make armour a **genuine sidegrade tradeoff**, not a strictly-better ladder — flat defense
  bought with speed — and, crucially, one that **shares the speed budget with boots**, so
  the two slots interact instead of being scored in isolation (the game's first true
  cross-slot decision).
- Move ordinary armour to **generation-placed, found-only, ≤1 per floor**, uniform pick
  among valid pieces, on a gentle depth ramp — mirroring ordinary boots but a touch more
  generous. Armour **leaves `gear_pool()`** entirely.
- Rework **floor 1** into a single coin-flip gift: Bone Sword *or* Leather Jerkin, 50/50 —
  the whole triad thesis ("do you start better at killing, or better at surviving?")
  compressed into the first pickup.
- Narrow the **vendor** to consumables only.
- **Graduate** thorns + wraithsilk up to the (future) magical T4 roster — they leave the
  ordinary tier now and return as magical identities in the roster spec.

## Non-goals (this plan)

- The **magical roster** — T4/T5 armour identities, mechanics, sprites, names, and the
  re-homing of thorns + wraithsilk. Its own spec, next.
- The **deep economy** — rarity, one-per-game uniqueness, death-persistence, and a
  collection gold star, mirroring boots' Phase 3A/3B. Its own plan.
- **Poltergeist armour-bypass** and a dual (wraith + poltergeist) Wraithsilk immunity —
  explicitly deferred by the user; lands with the magical roster at the earliest.
- The **full vendor rebalance** — the interim here is "consumables only"; the eventual
  "magical items at a very high price" idea is deferred and noted.
- Any change to weapons or boots.

## Design

### 1. Data model — the Armour class is unchanged

`Armour(key, name, tier, defense, speed_mod=0, trait=None, note="")` already carries
everything the ordinary tier needs; ordinary pieces simply set `trait=None`. Armour keeps
its existing enchant model — a shared `ALL_GEAR[key]` reference plus a per-player
`enchants[key]` bonus (raised by the DWEN *Scroll of Enchant Armour*) — so nothing about
enchanting changes.

Defense already funnels through the single `player.defense` property (player.py:116):

```python
d = (self.armour.defense + self.enchants.get(self.armour.key, 0)
     + self.boots.defense + ...)
```

so armour defense stacks with boots defense and the wraith **ignore-armour** path (which
suppresses the whole property) continues to ignore all of it — the intended behaviour.

### 2. The ordinary ladder — a sidegrade tradeoff on a shared speed budget

Four rungs. `rags` stays as the T0 starter (`STARTING[1]` is unchanged). The bare keys
`leather`/`mail`/`plate` are **reclaimed** for armour; boots keep their `boots_`-prefixed
keys, so the flat `ALL_GEAR` namespace has no clobber.

| tier | key | name | defense | speed | floor band |
|---|---|---|---|---|---|
| 0 | `rags` | Padded Rags | 0 | 0 | starter (unchanged) |
| 1 | `leather` | Leather Jerkin | +2 | 0 | 2–10 (also the floor-1 gift) |
| 2 | `mail` | Mail Shirt | +3 | −10 | 3–15 |
| 3 | `plate` | Full Plate | +4 | −20 | 5–15 |

**Removed:** `scale`, `chain`, `thorn`, `silk`. `thorn` (returns damage) and `silk`
(wraithsilk) do not die — their mechanics **graduate** to the magical T4 roster and are
absent from the game only until that spec ships (the accepted cost of shipping the ordinary
tier first).

The defining property is the **shared speed budget**: both `armour.speed_mod` and
`boots.speed` feed the one player-speed sum, so armour and boots spend from the same pool.
The same +4 total defense is reachable at three different speeds:

| build | total def | net speed |
|---|---|---|
| Leather Jerkin + Leather Boots | +2 | +10 |
| Mail Shirt + Leather Boots | +3 | 0 |
| Mail Shirt + Mail Boots | +4 | −10 |
| Full Plate + Leather Boots | +4 | −10 |
| Full Plate + Plate Boots | +6 | −30 |

That is a decision space, not a ladder: heavy armour negates most upper-floor hits
(ethereal monsters excepted) but the −30 speed is a real, sometimes-fatal cost. The tight
+2/+3/+4 defense spread is deliberate — magical armour will differentiate by **trait**, not
bigger numbers, keeping the creative headroom in the T4/T5 roster.

### 3. Distribution — generation-placed, found-only

A new `roll_floor_armour(rng, depth)` mirrors `roll_floor_boots`: at most **one** ordinary
armour per floor, chosen **uniformly** among the pieces valid at that depth, gated behind a
present-chance. It draws only on `(rng, depth)` — never the Kodex — so a seed's floors are
bit-identical for a blind and an omniscient hero (`TestKnowledgeIsNotPower` stays green).

- **Bands** (which pieces are valid): Leather 2–10, Mail 3–15, Plate 5–15. None on floor 1
  or past floor 15 — the deep floors are magical territory.
- **Present-chance** — a gentle upward ramp (higher than boots' flat 50%, climbing toward
  the weapon system's generosity):

  | floors | present-chance |
  |---|---|
  | 2–4 | 55% |
  | 5–8 | 65% |
  | 9–12 | 75% |
  | 13–15 | 80% |

  Per-flavour odds are `present × 1/(valid count)` — e.g. floor 5 (all three valid) ≈
  21.7% each; floor 15 (mail + plate) = 40% each.

- **Armour leaves `gear_pool()` entirely**, exactly as boots did. Consequence: with all
  three slots now generation-placed, `gear_pool` yields nothing, so `roll_loot`'s gear
  branch always falls back to its gold alternative — **chests, bodies, and generic floor
  drops now contain only gold and consumables.** All gear is found on the floor, placed at
  generation, scarce.
- **Placement** happens in `Level._generate` right after the ordinary-boots loop, on a free
  tile away from the gate.
- **Auto-swap** follows the boots rule: armour auto-equips **only over the T0 starter**
  (`rags`); once the player wears any T1+ armour, a found piece is left on the ground for a
  deliberate manual pickup, so the def/speed tradeoff is never silently resolved. (Today
  armour auto-swaps by tier — an assumption that is now false, since Full Plate is not an
  upgrade over a Leather Jerkin for a speed build.)

### 4. Floor 1 — the coin-flip gift

Floor 1 places **no random gear of any kind** — no weapon, no boot, no armour roll. In
their place is **exactly one guaranteed gift**, placed as far from the gate as the level
allows (the existing "floor 1 pays for curiosity" beat), which is a 50/50 coin-flip between:

- a **Bone Sword** (`bone_sword` — the plain T1 baseline weapon, no trait), or
- a **Leather Jerkin** (`leather` — the T1 entry armour, +2 def).

Consequences:

- The **guaranteed Bone Axe** retires: `roll_ordinary` returns `None` on floor 1 — no
  guaranteed axe *and* no random weapon roll (floor 1 must stay gear-free apart from the
  gift). Floors 2–7 keep their 80% ordinary-weapon rolls untouched.
- The **floor-1 gear gift drawn from `gear_pool`** retires and is replaced by this
  coin-flip. The once-per-game guard (`gift_claimed("floor1")`) and the far-from-gate
  placement are retained, so the gift never regrows on respawn (death cannot farm it).
- ~50% of runs leave floor 1 holding only the Rusted Shiv — accepted, and good difficulty
  texture: floor 1 is the softest floor, floors 2–7 hand out weapons at 80%/floor, and a +2
  jerkin is a strong survival start.

### 5. Vendor — consumables only

`Vendor._stock_up` drops its gear branch entirely and stocks only potions and scrolls; the
vendor's own docstring already claims "it has no interest whatsoever in your armour," so the
code simply catches up to the fiction. `GEAR_PRICE` and the `kind == "gear"` arm of
`price_of` become vestigial (armour is no longer in `gear_pool`, and magical armour is not
sold in this plan) — they may stay dormant or be trimmed at the plan's discretion; `buys()`
(consumables) is unchanged. The eventual richer vendor economy is deferred and noted.

### 6. Compatibility & migration

Deleting the `scale`/`chain`/`thorn`/`silk` keys from `ARMOURS`/`ALL_GEAR` is the one real
migration risk, because a **suspended run** can persist an armour key:
`Player.from_dict` does `ALL_GEAR[data["armour"]]`, which would `KeyError` if a pre-change
save has the player wearing a removed piece. The clean, low-risk handling is to **bump
`config.RUN_SAVE_VERSION`**: the loader already discards a run block whose version does not
match (falling back to a fresh run), so any pre-change suspended run is dropped gracefully
and "Continue" simply starts fresh — no crash, no half-migrated state. The Kodex
gear-discovery ledger and `gear_catalog` iterate only the live `ARMOURS` table, so a stale
recorded key for a deleted piece is inert rather than fatal (the plan should confirm no
lookup path dereferences a discovered key directly).

## Surfaces touched

- **`items.py`** — rewrite the `ARMOURS` table (rags T0; leather/mail/plate T1–3; drop
  scale/chain/thorn/silk); add `roll_floor_armour` + the armour bands; make `gear_pool`
  return nothing for armour (armour now generation-placed).
- **`dungeon.py`** — add the ordinary-armour placement loop after the boots loop; rework
  floor 1 (retire the guaranteed Bone Axe and the `gear_pool` gift; add the coin-flip
  gift).
- **`world.py`** — armour auto-swap becomes starter-only (mirror boots).
- **`vendor.py`** — stock consumables only (drop the gear branch).
- **`config.py`** — bump `RUN_SAVE_VERSION` to invalidate pre-change suspended runs.
- **`player.py`** — no change expected (`defense` already sums armour + boots + enchant;
  `rags` starter unchanged).
- **`tests.py`** — new tests (below).

## Testing considerations

- **Ladder & stacking:** each rung's `defense`/`speed`/`desc()` renders correctly; armour
  defense stacks additively with boots defense and the DWEN enchant; a wraith's
  ignore-armour path suppresses the *combined* defense, not just the armour term.
- **Shared speed budget:** Mail Shirt + Leather Boots nets 0 speed; Full Plate + Plate
  Boots nets −30; the min-speed floor still holds under stacked penalties.
- **Distribution:** ordinary armour appears only on floors 2–15, ≤1 per floor, uniform
  among valid, on the present-chance ramp; never on floor 1 or past 15; never in a vendor,
  chest, body, or generic loot drop.
- **Floor 1:** exactly one gift, 50/50 Bone Sword / Leather Jerkin, far from the gate,
  once-per-game (does not regrow on respawn); no Bone Axe; no other gear of any slot.
- **Vendor:** stocks consumables only, never gear.
- **Auto-swap:** a found armour auto-equips over the `rags` starter, but never
  auto-swaps once the player wears any T1+ armour (no silent speed downgrade).
- **Determinism:** blind vs. omniscient runs of a seed stay bit-identical
  (`roll_floor_armour` reads only `rng`/`depth`).
- **Save compatibility:** a pre-change suspended run (bumped `RUN_SAVE_VERSION`) is
  discarded gracefully — "Continue" starts fresh, no crash on a removed armour key.

## Open tunables (safe to settle in playtest)

- The ladder numbers (+2/+3/+4 defense; 0/−10/−20 speed) and the floor bands.
- The present-chance ramp (55 / 65 / 75 / 80) and its band edges.
- The 50/50 floor-1 split.
