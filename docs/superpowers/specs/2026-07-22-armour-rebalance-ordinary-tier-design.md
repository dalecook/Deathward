# Armour Rebalance — Ordinary Tier (Plan A)

**Date:** 2026-07-22
**Status:** SHIPPED — and **partly superseded.** See [the design archive note](../README.md).

> **Superseded below:** this spec lists `thorn` and `silk` under **Removed**. That was
> true on 2026-07-22. Both returned on 2026-07-23 as magical **T4** pieces (Thorned
> Cuirass, Wraithsilk) and are live in `deathward/items.py` today — exactly as the
> "graduate to the magical roster" note in the Scope paragraph anticipated. Everything
> else here still matches the code. `items.py` is the authority.
**Scope:** the first of the armour passes — the **final** leg of the gear triad, after
weapons and boots. This plan clean-slates the *ordinary* armour tier (leather/mail/plate),
moves armour to the same scarce, generation-placed, found-only model as weapons and boots,
reworks floor 1 into a single coin-flip gift, narrows the vendor to consumables, and pulls
armour into the **per-instance bonus model** so deep floors can hand out **masterwork**
(better-made, not magical) armour — the direct parallel to enhanced-Steel weapons. The
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
- Pull armour into the **per-instance bonus model** (like weapons) so deep floors (8–15)
  can hand out **masterwork** armour — a layered +1/+2 (never +3) whose odds climb with
  depth — the parallel to enhanced-Steel weapons. As a bonus, this closes the long-deferred
  `weapon-bonus-lootlist-edge`.
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

### 1. Data model — armour joins the per-instance bonus model

Today armour stores its enchant *player-side* in `enchants[armour.key]`, because armour
objects are shared `ALL_GEAR` references and cannot carry a per-instance `+n`. The code
already flags this as temporary — `player.py:152`: *"armour's [+n] still lives on the
enchants dict **until the armour rework**."* This plan is that rework, because masterwork
armour lying on the floor needs a per-instance place to keep its bonus.

`Armour` gains a `bonus` field and a `copy(bonus=n)` method, exactly like `Weapon`. The
consequences, all mirroring how weapons already work:

- **`player.defense`** reads `self.armour.bonus` (and `self.boots.defense`) instead of
  `self.enchants.get(self.armour.key, 0)`. It still funnels through the one property, so
  armour + masterwork + boots defense stack, and the wraith **ignore-armour** path (which
  suppresses the whole property) keeps ignoring all of it — the intended behaviour.
- **DWEN (*Scroll of Enchant Armour*)** raises the equipped `armour.bonus` (world.py:1887),
  mirroring KRAV raising `weapon.bonus`. No cap — earned power, like weapons.
- **Serialization** stores armour as `{key, bonus}` (player.py:168), like the weapon; the
  `enchants` dict retires (it is armour-only today — boots carry no bonus).
- **`gear_display`/`desc`** read `armour.bonus` for the shown `+n` (player.py:158).
- **Loot tuples widen** from `(kind, payload)` to carry a bonus for gear —
  `("gear", key, bonus)` with tolerant unpacking at the `loot_options` / `_consume_option`
  / `_put_back` sites — so a displaced enhanced piece keeps its `+n`. This **closes the
  long-deferred `weapon-bonus-lootlist-edge`** for weapons *and* armour in one move. (If
  this proves the heaviest part, it is the one piece that can split to an immediate
  follow-up; the masterwork *placement* itself uses `Drop.bonus`, which already exists.)

`Armour(key, name, tier, defense, speed_mod=0, trait=None, note="")` keeps its signature;
ordinary pieces set `trait=None`.

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
present-chance, and returned as a `(key, bonus)` pair. It draws only on `(rng, depth)` —
never the Kodex — so a seed's floors are bit-identical for a blind and an omniscient hero
(`TestKnowledgeIsNotPower` stays green), and a given floor regenerates the *same* masterwork
`+n` after death, so masterwork armour needs no special persistence.

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

- **Masterwork on deep floors (8–15) — a layered bonus, not a separate slot.** Weapons
  needed a separate deep-Steel slot because ordinary weapons cut off at floor 7; ordinary
  armour already runs to floor 15, so masterwork is simply *layered onto the piece
  `roll_floor_armour` already places*. When it drops a piece on floors 8+, roll its quality:
  - chance it is masterwork at all: `0.25 + (depth−8)·0.05` → **25% at floor 8 … 60% at
    floor 15**;
  - if masterwork, chance it is **+2** (else **+1**): `0.15 + (depth−8)·0.05` → **15% at
    floor 8 … 50% at floor 15**.

  **Never +3.** A found masterwork tops out at +2, so the heaviest ordinary fortress is Full
  Plate +2 (=+6 armour) plus Plate Boots (+2) = **+8 combined** — strong but mortal; +3
  would tip into near-invulnerability against everything non-ethereal. (DWEN can still push
  a piece past +2, but that is scarce, earned power, as with weapons.) Below floor 8 the
  bonus is always 0.

- **Armour leaves `gear_pool()` entirely**, exactly as boots did. Consequence: with all
  three slots now generation-placed, `gear_pool` yields nothing, so `roll_loot`'s gear
  branch always falls back to its gold alternative — **chests, bodies, and generic floor
  drops now contain only gold and consumables.** All gear is found on the floor, placed at
  generation, scarce.
- **Placement** happens in `Level._generate` right after the ordinary-boots loop, on a free
  tile away from the gate, as a `Drop(kind="gear", payload=key, bonus=n)` — `Drop.bonus`
  already exists from the weapon work and already round-trips through save/restore.
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

The bonus-model refactor reinforces this: the run save's shape changes anyway (armour goes
from a bare `key` to `{key, bonus}`, and the `enchants` dict is dropped), so bumping the
version is doubly warranted and a pre-change suspended run discards cleanly rather than
attempting a half-migration.

## Surfaces touched

- **`items.py`** — add `bonus` + `copy(bonus=n)` to `Armour`; rewrite the `ARMOURS` table
  (rags T0; leather/mail/plate T1–3; drop scale/chain/thorn/silk); add `roll_floor_armour`
  (returns `(key, bonus)`, with the masterwork roll on floors 8–15) + the armour bands; make
  `gear_pool` return nothing for armour (armour now generation-placed).
- **`player.py`** — `defense` reads `armour.bonus` (not `enchants`); serialize armour as
  `{key, bonus}` and retire the `enchants` dict; `gear_display` reads `armour.bonus`;
  `rags` starter unchanged.
- **`world.py`** — DWEN `enchant_armour` raises the equipped `armour.bonus`; widen gear
  loot tuples to `("gear", key, bonus)` with tolerant unpacking at `loot_options` /
  `_consume_option` / `_put_back` (closes the deferred bonus-loss edge); armour auto-swap
  becomes starter-only (mirror boots).
- **`dungeon.py`** — add the ordinary-armour placement loop after the boots loop (place a
  `Drop` carrying the rolled `bonus`); rework floor 1 (retire the guaranteed Bone Axe and
  the `gear_pool` gift; add the coin-flip gift).
- **`vendor.py`** — stock consumables only (drop the gear branch).
- **`config.py`** — bump `RUN_SAVE_VERSION` to invalidate pre-change suspended runs.
- **`tests.py`** — new tests (below).

## Testing considerations

- **Ladder & stacking:** each rung's `defense`/`speed`/`desc()` renders correctly; armour
  defense stacks additively with `armour.bonus` (masterwork/DWEN) and boots defense; a
  wraith's ignore-armour path suppresses the *combined* defense, not just the armour term.
- **Masterwork:** ordinary armour on floors 8–15 may roll +1 or +2 (never +3) at the
  depth-climbing odds; below floor 8 it is always +0; the `+n` adds to `player.defense` and
  shows in `gear_display`/`desc`.
- **Bonus model:** DWEN raises the equipped `armour.bonus` (uncapped); armour serializes as
  `{key, bonus}` and round-trips through suspend/resume; retiring the `enchants` dict breaks
  neither equip nor `defense`. A displaced enhanced piece put back into a container keeps its
  `+n` (the deferred `weapon-bonus-lootlist-edge` is closed for weapons and armour).
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
- The masterwork odds (masterwork chance `0.25 + (depth−8)·0.05`; +2 share
  `0.15 + (depth−8)·0.05`), capped at +2.
- The 50/50 floor-1 split.
- Whether DWEN should be hard-capped for armour (default: uncapped, matching weapons).
