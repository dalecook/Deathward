# Weapon Rebalance — Ordinary Weapons & Early Economy (Floors 1–8)

**Date:** 2026-07-17
**Status:** design, pending review
**Scope:** the first of two weapon passes. This one covers the *ordinary* weapon
tier and the loot economy that delivers it. The *magical* roster for floors 9–20 is
a deliberate follow-up, to be designed after this phase is playtested.

## Problem

Weapon power is dumped too early and too often. Tier 3 (the Flame Brand, the best
weapon in the game) can drop on floor **5**, so fifteen of the twenty floors have no
weapon progression left to find. Inside that first quarter the *average* damage jumps
steeply (shiv ~2 → sword ~3.5 → rapier/hammer ~5–6 → brand ~7.5) and each upgrade
arrives fast. Weapons are also cheap: gear is ~26% of *every* loot roll, and there are
many rolls per floor (floor drops + chests of 1–3 + monster bodies), so a weapon is a
thing you swap constantly rather than the find of the floor.

## Goals

- Spread weapon progression gently across the early floors instead of front-loading it.
- Make a weapon a *scarce, deliberate find*, not a frequent swap.
- Keep upgrades meaningful as **tactical decisions** (how you kill), not just bigger
  numbers — honouring the gear-triad thesis.
- Preserve the game's core invariants: **knowledge is information, never power**
  (weapon generation must stay independent of the Kodex), and blind-vs-omniscient runs
  of the same seed stay bit-identical.

## Non-goals (this phase)

- The expanded magical roster for floors 9–20 (next phase).
- Reconciling the **Steel Rapier's crit** into the new scheme — i.e. whether a finesse
  blade belongs in the ordinary tier — is deferred (next phase). This phase the Rapier
  simply stays a magical weapon for floors 8+. (Note: the old **Iron Warhammer is
  retired now**, since "hammer" becomes an ordinary bone/bronze/steel type — see §9.)
- Any change to armour or boots (separate task). They keep their current behaviour,
  including the existing `enchants`-dict path for Scroll of Enchant Armour.

## Design

### 1. Two weapon classes

- **Ordinary** — bone/bronze/steel swords, axes, hammers. The finds of floors 1–7.
  Can be found *enhanced* (better-made, non-magical). This phase builds these.
- **Magical** — Vampiric Kris, Flame Brand, Steel Rapier (and future deep-floor
  weapons). The finds of floors 8+. Always found *unenhanced*; enchantable only by
  scroll. Left as the existing three this phase.

### 2. The ordinary matrix — 3 types × 3 materials = 9 weapons

**Type sets the attack shape and a speed tax. Material raises the damage floor.**

| key | name | dmg | trait | speed tax |
|---|---|---|---|---|
| `bone_sword`   | Bone Sword     | 1–5 | — (single target) | 0 |
| `bone_axe`     | Bone Axe       | 1–5 | cleave | −15 |
| `bone_hammer`  | Bone Hammer    | 1–5 | stun   | −30 |
| `bronze_sword` | Bronze Sword   | 2–5 | — | 0 |
| `bronze_axe`   | Bronze Axe     | 2–5 | cleave | −15 |
| `bronze_hammer`| Bronze Hammer  | 2–5 | stun   | −30 |
| `steel_sword`  | Steel Sword    | 3–5 | — | 0 |
| `steel_axe`    | Steel Axe      | 3–5 | cleave | −15 |
| `steel_hammer` | Steel Hammer   | 3–5 | stun   | −30 |

The **Rusted Shiv** (`shiv`, 1–3, speed 0) stays as the starting junk weapon, ranked
below bone.

**Damage band is shared across types** — material is the *only* thing that changes the
numbers. Raising the floor while holding the ceiling at 5 nudges the average up
(bone 3 → bronze 3.5 → steel 4) but its main effect is to **kill the whiff**: a bone
weapon sometimes tickles for 1, steel is dependable. Upgrading reads as reliability,
not a power spike.

**Trait behaviours are unchanged from today:** cleave hits every adjacent enemy for
`max(1, dmg//2)`; stun is a 1-in-4 chance to stun for one turn. The plain sword has no
trait — it is the fast, reliable single-target pick.

### 3. Speed tax — the sole type differentiator

Weapons gain a `speed_mod`, same units as `boots.speed` and `armour.speed_mod`. Player
speed becomes:

```
speed = BASE_SPEED + boots.speed + armour.speed_mod + weapon.speed_mod   (min 30)
```

Because it is the same currency, **boots can buy the tax back**: a hammer (−30) under
Windwalkers (+40) nets +10; under Warden Plate (−18) drops to a deliberately sluggish
52. This gives the weapon a seat at the speed table that it did not have before, and
makes control/tank builds pay in tempo.

DPS ladder vs one normal-speed (100) monster, steel material (avg 4):
sword 4.0 (no downside) > axe 3.4 (but cleaves at 2+ bodies) > hammer 2.8 (but the
stun roughly negates a quarter of the target's own swings). No type is the raw-damage
winner; the choice is purely tactical. (If hammer's −30 feels too punishing in play,
soften to −25.)

### 4. Material banding across floors 1–7

Hard bands, type chosen at random within the band:

- **Bone:** floors 1–2
- **Bronze:** floors 3–4
- **Steel:** floors 5–7

(Adjustable at review — overlap, e.g. an occasional stray material one band off, is an
option if hard bands feel too clockwork.)

### 5. Enhancement — masterwork ordinary weapons

When a floor's weapon is *ordinary*, it may be a better-made version: **+1 or +2**,
non-magical. Enhancement raises **both lo and hi** by the bonus:

| | base | +1 | +2 |
|---|---|---|---|
| Bronze sword | 2–5 | 3–6 | 4–7 |
| Steel sword  | 3–5 | 4–6 | 5–7 |

- **Chance a found ordinary weapon is enhanced = `(depth − 1) × 10%`**: 0% on floor 1,
  10% on 2, … 60% on floor 7.
- **+1 vs +2 split (proposed, tunable):** when enhanced, 75% +1 / 25% +2. A top-end
  find on floor 7 (Steel +2, 5–7, avg 6) sits just under a base magical weapon like the
  Brand (avg 7.5), keeping magic clearly ahead.
- **Magical weapons are never found enhanced.** They can still be enchanted by scroll.

### 6. Unified per-instance bonus + persistence

**Current reality (verified):** enchantment does *not* survive death. `player.enchants`
is a per-run `{gear_key: +n}` dict, never serialised; the corpse stores only the
weapon's *key* (`leave_corpse` → `world.py:1775`); `new_run` builds a fresh Player, so
the bonus resets; reclaiming the corpse returns the *base* `ALL_GEAR[key]`
(`world.py:866`). The Warden-victory keep also re-equips via `ALL_GEAR[key]`
(`game.py:120`), dropping the bonus.

**New model:** the bonus becomes a **per-instance property on the weapon** (e.g.
`Weapon.bonus`, default 0), not a player-side dict. Found enhancement and scroll
enchantment are the *same* number. It travels with the weapon:

- **Found weapons are per-instance copies** carrying their own `bonus` (two Bronze
  Swords can be +1 and +2 independently — impossible under a key-keyed dict).
- **Scroll of Enchant Weapon** increments the *equipped weapon instance's* `bonus`
  (was: `enchants[weapon.key] += 1`). **No cap** — a Bone Axe +8 is a legitimate build.
- **`damage_roll`** uses `weapon.roll(rng) + weapon.bonus`; **`desc`/`gear_display`**
  render the bonus from the instance.
- **Persistence:** the corpse record (`leave_corpse`/`write_corpse`) stores
  `(weapon_key, bonus)`; reclaiming reconstructs the weapon copy with that bonus; the
  save round-trips it. The **victory-keep** path (`new_run(keep=...)`) also carries the
  bonus. Consistency everywhere: the number lives on the weapon.

Armour keeps the `enchants` dict for Scroll of Enchant Armour this phase (its
per-instance/persistence rework belongs to the armour task).

### 7. Weapon rarity — generation-placed, one per floor

Weapons are **placed once at floor generation**, not rolled from the generic loot
tables. At generation a floor decides: *does it have a weapon?* If so, roll its type,
material (by band), and enhancement (by depth). **Weapons are removed from the chest
and monster-body loot tables** so those sources cannot blow the one-per-floor cap;
chests and bodies keep giving gold and consumables. (Armour and boots will get the same
generation-placed treatment in their task, so a floor can still yield more than one
*gear piece* total — one weapon, one armour, one boots — just not two weapons.)

**Present-probability by depth:**

| Floors | class | present chance |
|---|---|---|
| 1 | ordinary | **100%** — fixed unenhanced Bone Axe |
| 2–8 | ordinary (2–7) / magical (8) | 80% |
| 9–15 | magical | 70% |
| 16–20 | magical | 60% |

### 8. Floor-1 guarantee

Floor 1 always places exactly one weapon: an **unenhanced Bone Axe**. This is the
safety valve against a run of empty floors stranding the player on the 1–3 shiv, and it
introduces cleave as the first lesson.

### 9. Reconciling existing weapons

- `sword` (Bronze Sword, 2–5) → folds into `bronze_sword` (same numbers, now speed 0).
- `axe` (Bone Axe, 1–7) → becomes `bone_axe` (1–5, cleave, −15).
- `hammer` (Iron Warhammer, 3–9, stun) → the hammer *type* is now bone/bronze/steel;
  "Iron Warhammer" is retired. (Its old stats are superseded.)
- `rapier` (crit), `brand` (burn), `kris` (lifesteal) → remain as the **magical** trio
  for floors 8+ this phase, found unenhanced, enchantable by scroll. Full magical-tier
  redesign (including whether crit belongs on an ordinary finesse blade) is next phase.

## Surfaces touched

- **`items.py`** — replace `WEAPONS` with the 9-weapon ordinary matrix + shiv + the 3
  magical weapons; add `speed_mod` and `bonus` to `Weapon`; add a per-instance copy
  helper; add weapon-generation (present-probability, banding, enhancement roll);
  remove weapons from `roll_loot`/`roll_chest`/`roll_monster_loot` outputs.
- **`player.py`** — `speed()` adds `weapon.speed_mod`; `damage_roll`/`gear_display`
  read `weapon.bonus` instead of `enchants[weapon.key]` for the weapon slot.
- **`world.py`** — Scroll of Enchant Weapon increments instance `bonus`; gear pickup /
  `equip` / drops thread the `bonus`; `leave_corpse` passes it.
- **`dungeon.py`** — place the floor's one weapon at generation; floor-1 guarantee.
- **`codex.py`** — corpse record stores and restores `bonus`; save format bump if
  needed for older corpses (default missing `bonus` to 0).
- **`game.py`** — `new_run(keep=...)` victory path carries the `bonus`.
- **`tests.py`** — update weapon-roster tests; add tests for the enhancement roll,
  per-instance bonus, corpse/victory persistence of `bonus`, one-weapon-per-floor cap,
  speed-tax math, and the bit-identical invariant with the new generation.

## Testing considerations

- **Determinism / bit-identical:** weapon generation must draw from the world RNG in a
  fixed order, independent of the Kodex, so a blind and an omniscient run of the same
  seed still produce identical floors. This is a load-bearing existing test.
- **Save migration:** an existing corpse saved without a `bonus` field must load as
  bonus 0 (a `LAYOUT_VERSION`/save-shape consideration).
- **No-cap enchant:** `desc`, `damage_roll` and the HUD must render arbitrary `+n`.

## Open tunables (safe to settle in playtest)

- Hammer speed tax −30 vs −25.
- +1/+2 enhancement split (proposed 75/25).
- Hard material bands vs slight overlap.
- Exact present-probability numbers.
