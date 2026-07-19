# Weapon Rebalance — Magical Roster & Deep Economy (Floors 8–20)

**Date:** 2026-07-19
**Status:** design, pending review
**Scope:** the second of the two weapon passes. Phase 1 built the *ordinary* tier
(floors 1–7) and the per-instance `bonus`/persistence machinery. This phase expands and
rebalances the *magical* tier (floors 8–20): a new Tier 5, twelve named magical weapons,
and the deep-floor loot economy that delivers them. Armour and boots remain out of scope.

## Problem

The magical tier is three weapons (Steel Rapier/crit, Flame Brand/burn, Vampiric
Kris/lifesteal) covering thirteen floors, drawn as a **flat, uniform-random pool** with
no depth progression. Two of the three (Brand, Kris) are clearly stronger than the third
yet share its tier. Descent past floor 8 stops feeling like it escalates, and there is
no scarcity or reward structure to make a deep-floor weapon feel like a *find*.

## Goals

- **A real magical progression** across floors 8–20 without dumping power early.
- **Two magical tiers** (4 and 5) where Tier 5 wins on **mechanical reach** (AoE + status
  on a crowd), not merely bigger single-hit numbers — honouring the gear-triad thesis
  that upgrades are *tactical decisions*, not inflation.
- **Scarcity as fiction:** the deeper you go, the fewer adventurers died there, so the
  less loot lies around — but what remains is *better* (masterwork steel, top-tier magic).
- **Weapons never a guaranteed find deep down.** A great weapon with poor armour still
  gets you killed, so the game need not hand them out; magical weapons are rare, and a run
  may see few or none.
- **Reuse existing systems** (burn, cleave, crit, lifesteal, stun, fear, poison, the
  `speed_mod` economy, the hardened stun/freeze code) rather than inventing a dozen new
  ones. Only three genuinely new mechanics.
- Preserve the core invariants: **knowledge is information, never power** (all generation
  and combat randomness draws from the world RNG, independent of the Kodex) and
  blind-vs-omniscient runs of a seed stay **bit-identical**.

## Non-goals (this phase)

- **Armour and boots** — untouched, separate future passes.
- **Building the mini-bosses.** Two weapons are mini-boss rewards, but the bosses
  themselves belong to the [add-minibosses-floors-8-15] task. This phase defines those two
  weapons, excludes them from the found pool, and leaves a clean drop-hook; until the
  bosses exist they are reachable only via the CTRL+12 weapon-bench cheat for testing.
- **New persistence plumbing** — phase 1 already made `bonus` per-instance and carried it
  through corpses, the victory-keep and the save. New weapons inherit all of it for free.

## Design

### 1. Two magical tiers and the power ordering

A new **Tier 5** sits above Tier 4. The full power ordering used by the "keep the better
weapon" corpse tie-break becomes:

```
shiv 0  <  bone 1  <  bronze 2  <  steel 3  <  magical-T4 4  <  magical-T5 5
```

The tie-break already compares `(tier, bonus)` as integers (`codex.leave_corpse`), so
adding tier 5 needs no new comparison logic — only the new weapons carry `tier=5`.

### 2. The through-line: focused (T4) vs unleashed (T5)

A magical weapon is built from an **effect family**. The **Tier 4** version delivers the
effect **focused** — single target, fast. The **Tier 5** version is the same fantasy
**unleashed** — it borrows an ordinary attack shape (usually the axe's **cleave**) so the
effect lands on a whole crowd. Tier 5's power is *reach*, not inflated single-hit numbers.

### 3. The roster — 7 Tier 4 + 6 Tier 5

All magical weapons are **found unenhanced** (`bonus = 0`) and **scroll-enchantable**
(uncapped, as phase 1). None carry a speed tax except **Windfang**, which carries a
speed *bonus*.

**Tier 4 — focused (avg damage in parens):**

| key | name | shape | dmg | trait(s) | notes |
|---|---|---|---|---|---|
| `rapier` | Razor Sharp Rapier | rapier | 4–6 (5) | crit | 1-in-4 doubles; spiky pure damage. Reuses existing `rapier` key. |
| `brand` | Flame Brand | sword | 4–8 (6) | burn | downgraded from 5–10. Reuses `brand` key. |
| `betrayers_edge` | Betrayer's Edge | sword | 4–6 (5) | enrage | chance to send the target into an Orc-like rage — it attacks any adjacent creature, **including you**. |
| `fulgurite` | Fulgurite | axe | 4–6 (5) | cleave + anti-incorporeal | cleaves; **double damage vs incorporeal** (wraith, poltergeist). The answer to armour-ignoring ghost mobs. |
| `winters_edge` | Winter's Edge | sword | 3–6 (4.5) | freeze | chance to freeze (one turn, reuses the `stunned` system). Control tax on damage. |
| `sacrificial_dagger` | Sacrificial Dagger | dagger | 3–5 (4) | lifesteal | low raw damage; sustain is the payoff. |
| `windfang` | Windfang | sword | **5–5 flat** | haste | `speed_mod = +20`. Low, *reliable* damage + extra tempo. **Floor-8 mini-boss reward.** |

**Tier 5 — unleashed:**

| key | name | shape | dmg | trait(s) | notes |
|---|---|---|---|---|---|
| `basilisk_maul` | Basilisk Maul | mace | 5–9 (7) | poison + stun | top single-target: venom that both envenoms and holds rigid. |
| `pyroclast` | Pyroclast | greataxe | 5–8 (6.5) | cleave + burn | ignites every body it cleaves. |
| `reapers_whisper` | Reaper's Whisper | scythe | 5–8 (6.5) | cleave + fear | scatters the whole crowd it reaps through. |
| `kris` | Vampiric Kris | dagger | 4–7 (5.5) | cleave + lifesteal | heals off **each** cleaved body — terrifying sustain in a swarm. Reuses `kris` key. |
| `glacial_flail` | Glacial Flail | flail | 4–7 (5.5) | cleave + freeze | freezes every adjacent enemy — room control. |
| `void_scimitar` | Scimitar of the Void | scimitar | **7–7 flat** | instakill | **10%** chance to delete a monster outright. **Floor-15 mini-boss reward.** |

The three existing keys (`rapier`, `brand`, `kris`) are **reused and retuned**; the other
ten are new keys.

### 4. Balance philosophy — utility, not inflation

**Magical weapons trade raw damage for their trait; they do not simply out-number the
deep enhanced Steel.** A scroll-fed Steel +3 (6–8, avg 7) remains a legitimate
pure-damage choice a player might keep over a utility magical weapon. Within a tier, raw
damage trades against utility, so **nothing is an auto-include**: the pure-damage picks
(Rapier, Brand, Basilisk) hit hardest; the control/sustain/haste picks (Winter's Edge,
Sacrificial Dagger, Windfang) hit softer and win on effect. All bands are playtest
tunables.

### 5. Traits — reused vs. new

| trait | status | mechanic |
|---|---|---|
| crit | reuse | 1-in-4 → ×2 damage (existing) |
| burn | reuse | ignite: `burning`, ~2 dmg/turn (existing) |
| lifesteal | reuse | heal `dmg // 2` (existing) |
| cleave | reuse | hits every adjacent enemy for `max(1, dmg//2)` (existing) |
| stun | reuse | the hardened player-turn stun (existing, phase-1.5 fix) |
| fear | reuse | the `feared` flee state from Scroll of Fear (existing) |
| **freeze** | reuse-as-theme | applies `stunned` (loses its turn), themed as cold; a chance on hit. Reads differently from the hammer because it rides a fast/AoE weapon. |
| **haste** | reuse | positive `weapon.speed_mod` (+20). No new code — phase 1 added `speed_mod`. |
| **cleave + status** | new combo | the "unleashed" rule: a Tier-5 cleave also applies its status (burn/freeze/fear) to **each** cleaved target, and lifesteal heals off each. Extends the existing cleave loop. |
| **enrage** | **new** | a `enraged` monster state: for its duration it attacks the nearest creature — **other monsters or the player** — reusing the Orc-style targeting. Chance on hit, timed. |
| **anti-incorporeal** | **new** | a new `incorporeal` marker on wraith + poltergeist; Fulgurite deals **double** damage to them. |
| **instakill (void)** | **new** | a % chance to remove a monster outright with **no corpse/Slain body and no dropped loot** (the void swallows it). Guard rails in §8. |
| poison (Basilisk) | **decision** | no lingering monster poison exists today. Default: a light `poisoned` DoT modelled on `burning`; alternative: reuse the venom damage burst. Open tunable. |

Default tunables for the new/parametric traits (all revisited in playtest):
freeze chance ~25% / 1 turn; enrage chance ~20% / ~6 turns; Fulgurite ×2 vs incorporeal;
Windfang `speed_mod +20`; Void instakill 10%.

### 6. Deep-floor weapon economy

Phase 1's single "magical when present" rule for floors 8+ is **replaced**:

- **Floors 1–7:** ordinary tier (phase 1, unchanged).
- **Floors 8–15 — up to *two* weapons (this band breaks the one-per-floor cap):**
  - a **non-magical slot**: *enhanced Steel only* — never base +0 this deep. Normally
    +1/+2, occasionally +3. Its present-chance **decays each floor to 0 at floor 15**.
    The **+3 (masterwork) chance itself climbs with depth** — a deeper corpse was a better
    adventurer. (Extends the phase-1 enhancement roll; scroll enchant stays uncapped.)
  - a **magical slot**: the rare magical roll (§7).
- **Floors 16–20:** the magical slot only (0 or 1 weapon).

Fiction: shallow floors are thick with the weapons of the many who died there; deep
floors hold few, but the few are masterwork or magical.

### 7. Magical rarity model

- **One magical slot per floor (8–20)** at a **rare** overall present-chance that gently
  **declines with depth** (fewer adventurers died deep). Absolute numbers are tunable; the
  intent is that a whole run may yield few or no magical weapons.
- **If a magical weapon is present, its tier is a depth crossover:** the Tier-4 share is
  high at floor 8 and falls toward floor 20; the Tier-5 share is low at floor 8 and rises.
  Both remain rare in absolute terms. Net effect: your chance of finding *a Tier 4* falls
  with depth while *a Tier 5* rises, and total magic stays scarce.
- **The specific weapon** is then chosen within the tier from the **findable** pool —
  i.e. **excluding the two mini-boss weapons**.
- All draws come from the world RNG in a fixed order, independent of the Kodex.

### 8. Mini-boss weapons and the void guard rails

**Windfang** (T4, floor-8 boss) and **Scimitar of the Void** (T5, floor-15 boss) are
excluded from the found pool entirely — obtainable only by defeating the matching
mini-boss. Because the mini-bosses are a separate task, this phase:

- adds both weapons to `WEAPONS` with their stats and sprites,
- excludes them from `roll_floor_weapon`'s findable pool,
- leaves a documented drop-hook for the mini-boss task to call,
- keeps them reachable via the **CTRL+12 weapon-bench cheat** so they can be playtested now.

The floor-8 boss should be **wind/speed-themed to match Windfang** (a swift blinker or an
aerial wraith-kin — "the gear matches the killer"); a note for the mini-boss task.

**Void instakill guard rails** (correctness, not just balance):
- **All bosses immune** — the Warden (else you skip the victory) and both mini-bosses.
- **Gift-carrying monsters immune** — the once-per-game gift item must never be voided.
- On a successful void: the monster is removed with **no Slain body, no drop, no loot** —
  a real cost that balances the power (voiding a loaded monster forfeits its haul).
- The 10% roll draws from the world RNG (bit-identical preserved). Starts at 10%,
  tunable down in playtest.

### 9. Renames, sprites, and Kodex

- **Key reuse:** `rapier` → Razor Sharp Rapier (still crit, retuned 4–6); `brand` → Flame
  Brand (retuned 4–8); `kris` → Vampiric Kris (now Tier 5, gains cleave, 4–7). Ten new
  keys for the rest. Old saves/corpses referencing `rapier`/`brand`/`kris` stay valid.
- **Sprites:** ten new `_weapon_sprite` branches (dagger, mace, flail, scythe, greataxe,
  scimitar, and the themed swords/axe), tinted to their element.
- **Kodex:** each new weapon and the three new mechanics (enrage, anti-incorporeal, void)
  want Kodex facts. Vampiric Kris's cleave gets an in-fiction justification: a blade so
  light, balanced and impossibly keen that a single draw carries clean through into the
  next body — and drinks from each.

### 10. Optional polish — flat-damage display

Flat-damage weapons (Windfang 5–5, Void 7–7) work with no code change (`randint(5,5)`),
but `desc()` would render "5-5 dmg". A one-line special-case rendering "5 dmg" when
`lo == hi` is a nice-to-have.

## Surfaces touched

- **`items.py`** — twelve magical weapons (3 retuned keys + 10 new); the tier-5 constant;
  `roll_floor_weapon` reworked into the two-slot deep economy (enhanced-steel slot with
  depth-decay + climbing +3; magical slot with declining presence + tier crossover;
  boss-locked exclusion); optional `desc()` flat-damage polish.
- **`monsters.py`** — `incorporeal` marker on wraith + poltergeist; the `enraged` state
  and its targeting; (if chosen) a `poisoned` DoT tick.
- **`world.py`** — trait resolution for the new/extended effects: freeze (apply `stunned`),
  enrage, anti-incorporeal damage multiplier, cleave-applies-status, the void instakill
  (with boss/gift immunity and no-loot removal), poison.
- **`dungeon.py`** — placement of up to two weapons on floors 8–15; one on 16–20.
- **`sprites.py`** — ten new weapon sprites.
- **`codex.py`** — Kodex facts for new weapons/mechanics; confirm the tier tie-break holds
  at tier 5.
- **`cheats.py` / weapon bench** — expose the twelve magical weapons (incl. the two
  boss-locked) for CTRL+12 testing.
- **`tests.py`** — roster shape and bands; two-slot deep economy; steel decay to 0 at
  floor 15; +3-climbs-with-depth; magical presence decline + tier crossover; boss-locked
  exclusion from the found pool; tier-5 corpse tie-break; each new mechanic (freeze,
  enrage, anti-incorporeal, void with immunities); flat-damage weapons; the bit-identical
  invariant with the new generation.

## Testing considerations

- **Determinism / bit-identical:** all new generation and the void roll must draw from the
  world RNG in a fixed order, independent of the Kodex. This is the load-bearing existing
  `TestKnowledgeIsNotPower` proof.
- **Boss/gift immunity to void** must be covered directly (Warden, mini-boss stand-in,
  gift-carrier) — these are correctness guards, not just balance.
- **Save compatibility:** new keys are additive; the three reused keys keep working, so
  existing corpses/saves load unchanged.
- **No-cap enchant** already renders arbitrary `+n` (phase 1) — new weapons inherit it.

## Open tunables (safe to settle in playtest)

- Magical present-chance curve (floors 8–20) and the T4/T5 crossover weights.
- Enhanced-steel non-magical slot: floor-8 start chance and the decay-to-0-at-15 curve;
  the +3 chance-by-depth curve.
- Void instakill 10% → lower if it evaporates too many deep elites.
- Freeze chance/duration; enrage chance/duration; Fulgurite's ×2 vs incorporeal;
  Windfang's +20 speed.
- Basilisk's poison model: new light DoT vs. reused venom burst.
- Every damage band in §3.
